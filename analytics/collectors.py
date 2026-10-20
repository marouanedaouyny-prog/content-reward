"""Validated local observations; no platform API access is implied."""

import uuid

from analytics.models import ClipPerformance

COLUMNS = ('clip_id', 'platform', 'collected_at', 'views', 'likes', 'comments', 'shares',
           'saves', 'average_watch_time', 'completion_rate', 'retention', 'followers_generated',
           'campaign_accepted', 'campaign_rejected', 'rejection_reason', 'reward_amount', 'provenance')


def collect_performance(store, observation):
    observation = observation if isinstance(observation, ClipPerformance) else ClipPerformance.model_validate(observation)
    store.get_clip(observation.clip_id)
    values = observation.model_dump(mode='json')
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL,
        f'{observation.clip_id}:{observation.platform}:{observation.collected_at}'))
    with store.connection(write=True) as db:
        old = db.execute('SELECT * FROM performance_metrics WHERE id=?', (identifier,)).fetchone()
        if old:
            if any(old[key] != values[key] for key in COLUMNS):
                raise ValueError('Observation timestamp already belongs to different metrics')
            return identifier
        db.execute('INSERT INTO performance_metrics VALUES (' + ','.join('?' for _ in range(18)) + ')',
                   (identifier, *(values[key] for key in COLUMNS)))
    return identifier


def latest_performance(store):
    with store.connection() as db:
        rows = db.execute('''SELECT p.* FROM performance_metrics p WHERE NOT EXISTS (
            SELECT 1 FROM performance_metrics newer WHERE newer.clip_id=p.clip_id
            AND newer.platform=p.platform AND newer.collected_at>p.collected_at)''').fetchall()
    results = []
    for row in rows:
        data = {key: row[key] for key in COLUMNS}
        for key in ('campaign_accepted', 'campaign_rejected'):
            if data[key] is not None:
                data[key] = bool(data[key])
        results.append(ClipPerformance.model_validate(data))
    return results
