"""Small, explainable adjustments based on independent observed clips."""

import math
from datetime import datetime, timezone
from statistics import mean

from analytics.collectors import independent_performance, latest_performance
from analytics.models import MeasurementContext
from app.core.config import load_settings
from clipping.library import IDS, route_niche


def _niche(clip):
    saved = clip.get('settings') or {}
    niche = saved.get('delivery_niche')
    return niche if niche in IDS else route_niche(saved.get('source') or {}, saved.get('niche'))


def _matches_pattern(clip, duration_seconds, opening_question):
    saved = clip.get('settings') or {}
    matches = []
    if duration_seconds is not None:
        duration = saved.get('source_clip_plan', {}).get('duration_seconds')
        if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                or not math.isfinite(duration) or duration <= 0):
            return None
        matches.append(int(duration // 10) == int(duration_seconds // 10))
    if opening_question is not None:
        question = saved.get('transcript_features', {}).get('opening_question')
        if not isinstance(question, bool):
            return None
        matches.append(question is opening_question)
    return all(matches)


def feedback_adjustment(store, *, caption_style, duration_seconds=None, opening_question=None,
                        niche=None, platform=None, settings=None, as_of=None, measurement_context=None):
    """Compare independent observed patterns within one niche/platform/style cohort."""
    settings = settings or load_settings()
    context = MeasurementContext.model_validate(measurement_context) if measurement_context is not None else None
    if context is None or context.cohort_key is None:
        return dict(adjustment=0, samples=0, comparison_samples=0, supported=False,
                    reason='learning_context_required',
                    basis='Choose an account, reporting window and known view definition before learning; '
                          'unknown observation context remains descriptive only.')
    clips = {clip['id']: clip for clip in store.list_clips()}
    records = []
    for observation in latest_performance(store, as_of=as_of, measurement_context=context):
        clip = clips.get(observation.clip_id)
        if (clip and clip['caption_style'] == caption_style
                and observation.views is not None and observation.views > 0
                and observation.measurement_context is not None
                and observation.measurement_context.cohort_key == context.cohort_key):
            records.append((clip, observation, _niche(clip)))
    chosen_niche = niche if niche in IDS else route_niche({}, niche) if niche else None
    if chosen_niche is None:
        available = {record[2] for record in records if record[2] != 'unclassified'}
        chosen_niche = next(iter(available)) if len(available) == 1 else None
    scoped = [record for record in records if record[2] == chosen_niche and record[2] != 'unclassified']
    if platform is None:
        platforms = {record[1].platform for record in scoped}
        platform = next(iter(platforms)) if len(platforms) == 1 else None
    scoped = [record for record in scoped if record[1].platform == platform]
    groups = {True: [], False: []}
    independent = independent_performance([record[1] for record in scoped], clips, settings=settings)
    for observation in independent:
        clip = clips[observation.clip_id]
        matched = _matches_pattern(clip, duration_seconds, opening_question)
        if matched is not None:
            groups[matched].append(observation)
    minimum = settings.feedback.minimum_samples
    followers = {group: [item for item in items if item.followers_generated is not None]
                 for group, items in groups.items()}
    use_followers = all(len(items) >= minimum for items in followers.values())
    measured = followers if use_followers else {
        group: [item for item in items if item.completion_rate is not None] for group, items in groups.items()}
    target, comparison = measured[True], measured[False]
    supported = bool(chosen_niche and chosen_niche != 'unclassified' and platform
                     and min(len(target), len(comparison)) >= minimum)
    reason = (None if supported else 'ambiguous_niche' if not chosen_niche or chosen_niche == 'unclassified'
              else 'ambiguous_platform' if not platform else 'insufficient_target_samples'
              if len(target) < minimum else 'insufficient_comparison_samples')

    def average(items):
        if not items:
            return None
        return (sum(item.followers_generated for item in items) / sum(item.views for item in items)
                if use_followers else mean(item.completion_rate for item in items))

    observed, baseline = average(target), average(comparison)
    shrinkage = min(len(target), len(comparison)) / (min(len(target), len(comparison)) + minimum)
    relative = ((observed - baseline) / (observed + baseline)
                if supported and observed + baseline > 0 else 0)
    adjustment = relative * shrinkage * settings.feedback.maximum_adjustment if supported else 0
    return dict(adjustment=round(adjustment, 6), samples=len(target), comparison_samples=len(comparison),
                observed_clips=len(scoped), independent_content_units=len(independent),
                average_completion_rate=mean([item.completion_rate for item in target
                    if item.completion_rate is not None]) if any(item.completion_rate is not None for item in target) else None,
                metric='followers_per_view' if use_followers else 'completion_rate',
                average_outcome=observed, comparison_outcome=baseline,
                smoothed_outcome=baseline + shrinkage * (observed - baseline) if supported else None,
                shrinkage_factor=shrinkage, positive_views=sum(item.views for item in target),
                comparison_positive_views=sum(item.views for item in comparison),
                cohort=dict(niche=chosen_niche, platform=platform, caption_style=caption_style,
                            duration_bucket=int(duration_seconds // 10) * 10 if duration_seconds is not None else None,
                            opening_question=opening_question, measurement_context=context.model_dump()),
                basis='Latest positive-view representatives of independent content in one niche/platform/style cohort; '
                      'materially overlapping source windows or matching export hashes count once, '
                      'and unknown identities are excluded; '
                      'account, reporting window, view definition and definition version must match exactly; '
                      'compare with independent other-pattern clips, prefer supported follower conversion, '
                      'and shrink the relative association by independent sample support. '
                      'Manual/imported observations are not platform verified; correlation is not causation.',
                minimum_samples=minimum, supported=supported, reason=reason)


def adjust_candidate(candidate, feedback):
    original = candidate.get('selection', {}).get('score', 0)
    adjusted = max(0, min(1, original + feedback['adjustment']))
    return {**candidate, 'feedback': {**feedback, 'original_score': original, 'adjusted_score': adjusted}}


def feedback_for_order(controller):
    cache = {}
    settings = load_settings()
    cutoff = controller.state.get('created_at') or datetime.now(timezone.utc)
    campaign = controller.store.get_campaign(controller.config.campaign_id) if controller.config.campaign_id else None
    platform = campaign.platform if campaign else None
    with controller.store.connection() as db:
        has_history = db.execute('SELECT 1 FROM performance_metrics LIMIT 1').fetchone() is not None

    def evaluate(candidate):
        context = getattr(controller.config, 'measurement_context', None)
        if context is None:
            return dict(adjustment=0, samples=0, supported=False, reason='learning_context_required',
                        basis='This saved order has no explicit learning account/window/view-definition context.')
        if not has_history:
            return dict(adjustment=0, samples=0, supported=False,
                        basis='No measured historical performance; base selection score is unchanged.')
        duration = candidate['clip_plan']['duration_seconds']
        question = candidate.get('transcript_features', {}).get('opening_question')
        niche = route_niche(controller.state.get('source_selection') or {}, controller.config.niche)
        if niche == 'unclassified':
            return dict(adjustment=0, samples=0, supported=False,
                        basis='Candidate niche is ambiguous; no performance cohort can be matched.')
        key = (int(duration // 10), question, niche, platform)
        if key not in cache:
            cache[key] = feedback_adjustment(controller.store, caption_style=controller.config.caption_style,
                duration_seconds=duration, opening_question=question, niche=niche, platform=platform,
                settings=settings, as_of=cutoff, measurement_context=context)
        return cache[key]
    return evaluate
