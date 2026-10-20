from statistics import mean

from analytics.collectors import latest_performance


def business_metrics(store):
    clips = store.list_clips()
    observations = latest_performance(store)
    per_clip = {}
    for item in observations:
        if item.views is not None:
            per_clip.setdefault(item.clip_id, []).append(item.views)
    views = [sum(values) for values in per_clip.values()]
    with store.connection() as db:
        publications = [dict(row) for row in db.execute('SELECT status FROM publications')]
        durations = [row[0] for row in db.execute("SELECT json_extract(data,'$.duration_ms') FROM pipeline_events WHERE json_extract(data,'$.duration_ms') IS NOT NULL")]
    actual_publications = [p for p in publications if p['status'] in ('PUBLISHED', 'PUBLISH_FAILED')]
    decisions = [o for o in observations if o.campaign_accepted is not None or o.campaign_rejected is not None]
    reward_values = [o.reward_amount for o in observations if o.reward_amount is not None]
    days = {clip['created_at'][:10] for clip in clips}
    rewards_by_source, rewards_by_niche = {}, {}
    clip_lookup = {clip['id']: clip for clip in clips}
    for item in observations:
        if item.reward_amount is None or item.clip_id not in clip_lookup:
            continue
        clip = clip_lookup[item.clip_id]
        if clip['source_id']:
            rewards_by_source.setdefault(clip['source_id'], []).append(item.reward_amount)
        niche = clip['settings'].get('niche')
        if niche:
            rewards_by_niche.setdefault(niche, []).append(item.reward_amount)
    report = dict(clips_generated=len(clips), clips_generated_per_day=len(clips) / len(days) if days else 0,
        measured_clips=len(per_clip), views_per_clip=mean(views) if views else None,
        prepared_publications=sum(p['status'] == 'READY' for p in publications),
        publish_success_rate=(sum(p['status'] == 'PUBLISHED' for p in actual_publications) / len(actual_publications)
                              if actual_publications else None),
        campaign_acceptance_rate=(sum(o.campaign_accepted is True for o in decisions) / len(decisions) if decisions else None),
        reward_per_clip=str(sum(reward_values) / len(reward_values)) if reward_values else None,
        reward_observations=len(reward_values),
        reward_by_source={key: str(sum(values)) for key, values in rewards_by_source.items()},
        reward_by_niche={key: str(sum(values)) for key, values in rewards_by_niche.items()},
        reward_per_hour=None,
        average_recorded_stage_duration_ms=mean(durations) if durations else None,
        limitations=['Metrics are imported/manual observations, not verified platform collection.',
                     'Unknown views, rewards and rates remain null; absent payments are not zero.',
                     'Reward observations are not a payment ledger; compute efficiency needs timed run evidence.'])
    return report
