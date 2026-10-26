import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean

from analytics.collectors import independent_performance, latest_performance
from analytics.models import MeasurementContext
from app.repositories.cache import CacheRepository
from clipping.library import route_niche


def _report_cohorts(store, minimum_samples, measurement_context, as_of, platform, niche):
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
        raise ValueError('The minimum independent sample count must be a positive integer')
    context = MeasurementContext.model_validate(measurement_context) if measurement_context is not None else None
    if context is None or context.cohort_key is None:
        return context, {}, {}, 'learning_context_required'
    clips = {clip['id']: clip for clip in store.list_clips()}
    selected_niche = route_niche({}, niche) if niche is not None else None
    groups = defaultdict(list)
    for observation in latest_performance(store, as_of=as_of, measurement_context=context):
        clip = clips.get(observation.clip_id)
        if clip is None or platform is not None and observation.platform != platform:
            continue
        saved = clip.get('settings') or {}
        clip_niche = (route_niche({}, saved['delivery_niche']) if saved.get('delivery_niche')
                      else route_niche(saved.get('source') or {}, saved.get('niche')))
        if selected_niche is not None and clip_niche != selected_niche:
            continue
        groups[(observation.platform, clip_niche)].append(observation)
    if selected_niche == 'unclassified' or any(key[1] == 'unclassified' for key in groups):
        reason = 'ambiguous_niche'
    elif len({key[0] for key in groups}) > 1:
        reason = 'ambiguous_platform'
    elif len(groups) > 1:
        reason = 'ambiguous_niche'
    else:
        reason = None if groups else 'insufficient_samples'
    return context, clips, groups, reason


def _cohort_metadata(context, key):
    return {'cohort': {'platform': key[0], 'niche': key[1]},
            'cohort_key': [key[0], key[1], *context.cohort_key]}


def _hashtag_cohort(observations, minimum_samples, prior_views):
    recent_posts = [' '.join(item.hashtags) for item in sorted(
        (item for item in observations if item.hashtags is not None),
        key=lambda item: item.collected_at, reverse=True)[:20]]
    measured = [item for item in observations if item.hashtags is not None
                and item.views is not None and item.views > 0 and item.followers_generated is not None]
    total_views = sum(item.views for item in measured)
    total_followers = sum(item.followers_generated for item in measured)
    baseline = total_followers / total_views if total_views else None
    by_tag = {}
    for item in measured:
        for tag in {tag.casefold() for tag in item.hashtags}:
            clips = by_tag.setdefault(tag, {})
            clips[item.clip_id] = (clips.get(item.clip_id, (0, 0))[0] + item.followers_generated,
                                   clips.get(item.clip_id, (0, 0))[1] + item.views)

    tags, scores = {}, {}
    for tag, clips in by_tag.items():
        followers = sum(value[0] for value in clips.values())
        views = sum(value[1] for value in clips.values())
        rate = followers / views * 1000 if views else None
        score = None
        if len(clips) >= minimum_samples and baseline and baseline > 0:
            smoothed_rate = (followers + baseline * prior_views) / (views + prior_views) * 1000
            score = round(max(0.0, min(1.0, smoothed_rate / (baseline * 2000))), 4)
            scores[tag.lstrip('#')] = score
        tags[tag] = {'clip_count': len(clips), 'views': views,
                     'followers_per_1000_views': round(rate, 4) if rate is not None else None,
                     'score': score}

    return {'status': 'measured' if scores else 'insufficient_data',
            'reason': None if scores else 'insufficient_samples' if not any(
                len(clips) >= minimum_samples for clips in by_tag.values()) else 'zero_baseline',
            'minimum_independent_clips': minimum_samples,
            'baseline_followers_per_1000_views': round(baseline * 1000, 4) if baseline is not None else None,
            'tags': tags, 'scores': scores, 'recent_posts': recent_posts}


def observed_hashtag_history(store, platform, minimum_samples=3, prior_views=10_000, *,
                             measurement_context=None, as_of=None, niche=None):
    """Learn tag priors only within an explicit account/window and one niche."""
    if (isinstance(prior_views, bool) or not isinstance(prior_views, (int, float))
            or not math.isfinite(prior_views) or prior_views < 0):
        raise ValueError('The prior view count must be finite and nonnegative')
    context, clips, groups, reason = _report_cohorts(
        store, minimum_samples, measurement_context, as_of, platform, niche)
    report = _hashtag_cohort([], minimum_samples, prior_views)
    report.update(reason=reason, measurement_context=context.model_dump() if context else None,
                  cohort=None, cohort_key=None, cohorts=[])
    for key, observations in sorted(groups.items()):
        if key[1] == 'unclassified':
            continue
        cohort = _hashtag_cohort(independent_performance(observations, clips), minimum_samples, prior_views)
        cohort.update(_cohort_metadata(context, key))
        report['cohorts'].append(cohort)
    if reason is None:
        report.update(report['cohorts'][0])
    report['limitations'] = [
        'Choose an account, reporting window and known view definition before learning; definition versions must match exactly.',
        'Hashtag scores and freshness use latest independent content in one platform/niche cohort at the cutoff; unknown identities are excluded.',
        'Only manual/imported observations with explicit tags, known positive views and known follower gains support scores.',
        'Per-tag scores are smoothed toward the matching cohort baseline; associations are not causal and supplied tags are not platform verified.']
    return report


def _growth_cohort(observations, clips, minimum_samples, platform):
    observations = [item for item in observations if item.views is not None and item.views > 0
                    and item.followers_generated is not None]

    measured = []
    duration_groups, hook_groups, hashtag_groups, cta_groups = {}, {}, {}, {}
    for observation in observations:
        clip_id = observation.clip_id
        followers, views = observation.followers_generated, observation.views
        clip = clips[clip_id]
        rate = round(followers / views * 1000, 4)
        measured.append({'clip_id': clip_id, 'followers_per_1000_views': rate,
                         'views': views, 'followers': followers})
        duration = (clip.get('settings') or {}).get('source_clip_plan', {}).get('duration_seconds')
        if (not isinstance(duration, bool) and isinstance(duration, (int, float))
                and math.isfinite(duration) and duration > 0):
            bucket = int(duration // 5) * 5
            totals = duration_groups.setdefault(bucket, [0, 0, 0])
            totals[0] += followers
            totals[1] += views
            totals[2] += 1
        if observation.hashtags is not None:
            tags = tuple(sorted({tag.casefold() for tag in observation.hashtags}))
            hashtag_groups.setdefault(tags, []).append(observation)
        if observation.cta_used is not None:
            cta_groups.setdefault(observation.cta_used, []).append(observation)
        growth = ((clip.get('settings') or {}).get('growth') or {})
        hook_type = (growth.get('hook') or {}).get('hook_type')
        if isinstance(hook_type, str) and hook_type.strip():
            totals = hook_groups.setdefault(hook_type.strip(), [0, 0, 0])
            totals[0] += followers
            totals[1] += views
            totals[2] += 1

    enough_data = len(measured) >= minimum_samples
    patterns = [dict(duration_seconds=duration, clip_count=count,
                     followers_per_1000_views=round(followers / views * 1000, 4))
                for duration, (followers, views, count) in sorted(duration_groups.items())
                if count >= minimum_samples and views > 0]
    hook_patterns = [dict(hook_type=hook_type, clip_count=count,
                          followers_per_1000_views=round(followers / views * 1000, 4))
                     for hook_type, (followers, views, count) in sorted(hook_groups.items())
                     if count >= minimum_samples and views > 0]
    hashtag_patterns = []
    for tags, values in sorted(hashtag_groups.items()):
        followers = sum(value.followers_generated for value in values)
        views = sum(value.views for value in values)
        if len(values) >= minimum_samples and views > 0:
            hashtag_patterns.append({'platform': platform, 'hashtags': list(tags),
                                     'clip_count': len(values),
                                     'followers_per_1000_views': round(followers / views * 1000, 4)})
    cta_patterns = []
    for cta, values in sorted(cta_groups.items()):
        followers = sum(value.followers_generated for value in values)
        views = sum(value.views for value in values)
        if len(values) >= minimum_samples and views > 0:
            cta_patterns.append({'platform': platform, 'cta': cta, 'clip_count': len(values),
                                 'followers_per_1000_views': round(followers / views * 1000, 4)})
    measured.sort(key=lambda item: (item['followers_per_1000_views'], item['views']), reverse=True)
    return {'status': 'measured' if enough_data else 'insufficient_data',
            'reason': None if enough_data else 'insufficient_samples',
            'minimum_independent_clips': minimum_samples, 'measured_clip_count': len(measured),
            'best_clips': measured[:5] if enough_data else [],
            'worst_clips': list(reversed(measured[-5:])) if enough_data else [],
            'duration_patterns': patterns if enough_data else [],
            'hook_patterns': hook_patterns if enough_data else [],
            'hashtag_patterns': hashtag_patterns if enough_data else [],
            'cta_patterns': cta_patterns if enough_data else []}


def growth_insights(store, minimum_samples=3, *, measurement_context=None, as_of=None,
                    platform=None, niche=None):
    """Report independent follower associations within comparable cohorts."""
    context, clips, groups, reason = _report_cohorts(
        store, minimum_samples, measurement_context, as_of, platform, niche)
    report = _growth_cohort([], clips, minimum_samples, platform)
    report.update(reason=reason, measurement_context=context.model_dump() if context else None,
                  cohort=None, cohort_key=None, cohorts=[])
    for key, observations in sorted(groups.items()):
        if key[1] == 'unclassified':
            continue
        cohort = _growth_cohort(independent_performance(observations, clips), clips, minimum_samples, key[0])
        cohort.update(_cohort_metadata(context, key))
        report['cohorts'].append(cohort)
    if reason is None:
        report.update(report['cohorts'][0])
    else:
        report['measured_clip_count'] = sum(cohort['measured_clip_count'] for cohort in report['cohorts'])
    report['limitations'] = [
        'Choose an account, reporting window and known view definition before learning; definition versions must match exactly.',
        'Only latest independent content within one platform/niche cohort at the cutoff supports comparisons; unknown identities are excluded.',
        'For mixed cohorts, the measured clip count sums independent content within each cohort; the same content can appear on several platforms.',
        'Follower conversion requires known positive views and known follower gains; each reported pattern needs its own independent sample support.',
        'Duration, rule-based hook, hashtag and CTA associations are descriptive and do not establish causation or verified platform collection.']
    return report


def business_metrics(store):
    cache = CacheRepository(store).stats()
    clips = store.list_clips()
    observations = latest_performance(store)
    per_clip = {}
    for item in observations:
        if item.views is not None:
            per_clip.setdefault(item.clip_id, []).append(item.views)
    views = [sum(values) for values in per_clip.values()]
    follow_pairs = {}
    visit_values = []
    for observation in observations:
        if observation.profile_visits is not None:
            visit_values.append(observation.profile_visits)
        if (observation.views is not None and observation.views > 0
                and observation.followers_generated is not None):
            totals = follow_pairs.setdefault(observation.clip_id, [0, 0])
            totals[0] += observation.followers_generated
            totals[1] += observation.views
    followers_by_clip = {clip_id: round(followers / clip_views * 1000, 4)
                         for clip_id, (followers, clip_views) in follow_pairs.items() if clip_views > 0}
    follow_views = sum(values[1] for values in follow_pairs.values())
    follow_count = len(follow_pairs)
    followers_per_1000 = (round(sum(values[0] for values in follow_pairs.values())
                                / follow_views * 1000, 4) if follow_views > 0 else None)
    with store.connection() as db:
        publications = [dict(row) for row in db.execute('SELECT status,metadata FROM publications')]
        duration_rows = db.execute("""SELECT order_id,json_extract(data,'$.duration_ms') AS duration_ms
            FROM pipeline_events WHERE order_id IS NOT NULL
            AND json_extract(data,'$.duration_ms') IS NOT NULL""").fetchall()
        render_attempts = db.execute("SELECT count(*) FROM pipeline_events WHERE event='render_started'").fetchone()[0]
        successful_renders = db.execute("SELECT count(*) FROM pipeline_events WHERE event='render_succeeded'").fetchone()[0]
    actual_publications = []
    for publication in publications:
        evidence = json.loads(publication['metadata'])
        if (publication['status'] in ('PUBLISHED', 'PUBLISH_FAILED')
                and evidence.get('adapter') in ('youtube', 'instagram', 'tiktok')
                and evidence.get('network_attempted') is True):
            actual_publications.append(publication)
    decisions = [o for o in observations if o.campaign_accepted is True or o.campaign_rejected is True]
    rewards_per_clip = {}
    for observation in observations:
        if observation.reward_amount is not None:
            rewards_per_clip[observation.clip_id] = (
                rewards_per_clip.get(observation.clip_id, 0) + observation.reward_amount
            )
    reward_totals = list(rewards_per_clip.values())
    clip_dates = sorted(clip['created_at'][:10] for clip in clips)
    window_days = ((date.fromisoformat(clip_dates[-1]) - date.fromisoformat(clip_dates[0])).days + 1
                   if clip_dates else 0)
    durations_by_order = {}
    for row in duration_rows:
        durations_by_order[row['order_id']] = durations_by_order.get(row['order_id'], 0) + row['duration_ms']
    pipeline_durations = list(durations_by_order.values())
    rewards_by_source, rewards_by_niche, rewards_by_order = {}, {}, {}
    clip_lookup = {clip['id']: clip for clip in clips}
    for item in observations:
        if item.reward_amount is None or item.clip_id not in clip_lookup:
            continue
        clip = clip_lookup[item.clip_id]
        rewards_by_order.setdefault(clip['order_id'], []).append(item.reward_amount)
        if clip['source_id']:
            rewards_by_source.setdefault(clip['source_id'], []).append(item.reward_amount)
        niche = clip['settings'].get('niche')
        if niche:
            rewards_by_niche.setdefault(niche, []).append(item.reward_amount)
    measured_orders = set(rewards_by_order) & set(durations_by_order)
    measured_duration = sum(durations_by_order[order] for order in measured_orders)
    reward_per_hour = (float(sum(sum(rewards_by_order[order]) for order in measured_orders)) /
        (measured_duration / 3600000) if measured_duration > 0 else None)
    report = dict(clips_generated=len(clips),
        clips_generated_per_day=len(clips) / window_days if window_days else 0,
        reporting_window_days=window_days,
        measured_clips=len(per_clip), views_per_clip=mean(views) if views else None,
        profile_visits=sum(visit_values) if visit_values else None,
        follow_conversion_samples=follow_count,
        follow_conversion_rate=(round(followers_per_1000 / 1000, 6) if followers_per_1000 is not None else None),
        followers_per_1000_views=followers_per_1000,
        followers_per_1000_views_by_clip=followers_by_clip,
        successful_render_rate=(successful_renders / render_attempts if render_attempts else None),
        render_attempts=render_attempts,
        prepared_publications=sum(p['status'] == 'READY' for p in publications),
        publish_success_rate=(sum(p['status'] == 'PUBLISHED' for p in actual_publications) / len(actual_publications)
                              if actual_publications else None),
        publication_attempts=len(actual_publications), campaign_decisions=len(decisions),
        campaign_acceptance_rate=(sum(o.campaign_accepted is True for o in decisions) / len(decisions) if decisions else None),
        reward_per_clip=str(sum(reward_totals) / len(reward_totals)) if reward_totals else None,
        reward_observations=sum(o.reward_amount is not None for o in observations),
        reward_by_source={key: str(sum(values)) for key, values in rewards_by_source.items()},
        reward_by_niche={key: str(sum(values)) for key, values in rewards_by_niche.items()},
        reward_per_hour=reward_per_hour,
        average_pipeline_duration_ms=mean(pipeline_durations) if pipeline_durations else None,
        cache_requests=cache['requests'], cache_hits=cache['hits'], cache_misses=cache['misses'],
        cache_hit_rate=cache['hit_rate'], cache_bytes_reused=cache['bytes_reused'],
        cache_by_kind=cache['by_kind'],
        performance_periods=aggregate_performance_periods(observations),
        limitations=['Metrics are imported/manual observations, not verified platform collection.',
                     'Unknown views, rewards and rates remain null; absent payments are not zero.',
                     'Follower conversion includes only latest clip/platform observations with known positive views and known follower gains; rates are view-weighted.',
                     'The generation rate uses the inclusive span from first to latest recorded clip.',
                     'Render rates count measured render-stage attempts; interrupted attempts count as unsuccessful until resumed.',
                     'Reward/hour includes only orders with both clip-linked reward observations and recorded run duration.',
                     'Cache efficiency covers instrumented bounded-section lookups since telemetry was enabled; it does not estimate time saved.'])
    return report


def aggregate_performance_periods(observations):
    """Aggregate latest clip/platform observations into UTC daily, weekly and monthly series."""
    groups = {name: defaultdict(list) for name in ('daily', 'weekly', 'monthly')}
    for observation in observations:
        collected = datetime.fromisoformat(observation.collected_at.replace('Z', '+00:00')).astimezone(timezone.utc)
        day = collected.date()
        keys = {'daily': day.isoformat(),
                'weekly': (day - timedelta(days=day.weekday())).isoformat(),
                'monthly': date(day.year, day.month, 1).isoformat()}
        for period, start in keys.items():
            groups[period][start].append(observation)

    result = {}
    for period, buckets in groups.items():
        records = []
        for start, values in sorted(buckets.items()):
            views = [item.views for item in values if item.views is not None]
            followers = [item.followers_generated for item in values if item.followers_generated is not None]
            visits = [item.profile_visits for item in values if item.profile_visits is not None]
            rates = [(item.followers_generated, item.views) for item in values
                     if item.followers_generated is not None and item.views is not None and item.views > 0]
            completions = [item.completion_rate for item in values if item.completion_rate is not None]
            watch_times = [item.average_watch_time for item in values if item.average_watch_time is not None]
            view_total = sum(views)
            rate_views = sum(pair[1] for pair in rates)
            records.append({'period_start': start, 'observations': len(values),
                'measured_clips': len({item.clip_id for item in values}),
                'views_samples': len(views),
                'views': view_total if views else None,
                'followers_samples': len(followers),
                'followers_generated': sum(followers) if followers else None,
                'follower_conversion_samples': len(rates),
                'followers_per_1000_views': (round(sum(pair[0] for pair in rates) / rate_views * 1000, 4)
                                             if rate_views else None),
                'profile_visits_samples': len(visits),
                'profile_visits': sum(visits) if visits else None,
                'completion_rate_samples': len(completions),
                'completion_rate_mean': mean(completions) if completions else None,
                'average_watch_time_samples': len(watch_times),
                'average_watch_time_mean': mean(watch_times) if watch_times else None})
        result[period] = records
    return result
