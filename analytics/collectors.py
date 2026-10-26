"""Validated local observations; no platform API access is implied."""

import json
import heapq
import math
import re
import uuid
from datetime import datetime, timezone

from analytics.models import ClipPerformance, MeasurementContext
from app.core.config import load_settings

COLUMNS = ('clip_id', 'platform', 'collected_at', 'views', 'likes', 'comments', 'shares',
           'saves', 'average_watch_time', 'completion_rate', 'retention', 'followers_generated',
           'campaign_accepted', 'campaign_rejected', 'rejection_reason', 'reward_amount', 'provenance',
           'profile_visits', 'hashtags', 'cta_used', 'measurement_context',
           'average_view_percentage', 'audience_watch_ratio')
JSON_COLUMNS = ('hashtags', 'measurement_context')


def _observation_data(row):
    data = {key: row[key] for key in COLUMNS}
    for key in JSON_COLUMNS:
        data[key] = json.loads(data[key]) if data[key] is not None else None
    return data


def collect_performance(store, observation):
    observation = observation if isinstance(observation, ClipPerformance) else ClipPerformance.model_validate(observation)
    store.get_clip(observation.clip_id)
    values = observation.model_dump(mode='json')
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL,
        f'{observation.clip_id}:{observation.platform}:{observation.collected_at}'))
    with store.connection(write=True) as db:
        old = db.execute('SELECT * FROM performance_metrics WHERE id=?', (identifier,)).fetchone()
        if old:
            existing = _observation_data(old)
            if any(existing[key] != values[key] for key in COLUMNS):
                raise ValueError('Observation timestamp already belongs to different metrics')
            return identifier
        stored = [json.dumps(values[key], ensure_ascii=True, allow_nan=False)
                  if key in JSON_COLUMNS and values[key] is not None else values[key] for key in COLUMNS]
        db.execute('INSERT INTO performance_metrics (id,' + ','.join(COLUMNS) + ') VALUES ('
                   + ','.join('?' for _ in range(len(COLUMNS) + 1)) + ')',
                   (identifier, *stored))
    return identifier


def latest_performance(store, *, as_of=None, measurement_context=None):
    """Latest clip/platform snapshots known at an aware historical cutoff."""
    cutoff = datetime.now(timezone.utc) if as_of is None else as_of
    if isinstance(cutoff, str):
        cutoff = datetime.fromisoformat(cutoff.replace('Z', '+00:00'))
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() is None:
        raise ValueError('Observation cutoff needs a collection timezone')
    cutoff = cutoff.astimezone(timezone.utc).isoformat()
    scope = ''
    parameters = [cutoff]
    if measurement_context is not None:
        context = MeasurementContext.model_validate(measurement_context)
        scope = '''AND json_extract(measurement_context,'$.account_id') IS ?
                   AND json_extract(measurement_context,'$.reporting_window_hours') IS ?
                   AND json_extract(measurement_context,'$.view_definition') IS ?
                   AND json_extract(measurement_context,'$.definition_version') IS ?'''
        parameters.extend((context.account_id, context.reporting_window_hours,
                           context.view_definition, context.definition_version))
    with store.connection() as db:
        rows = db.execute('''WITH scoped AS (SELECT * FROM performance_metrics WHERE collected_at<=? '''
            + scope + ''') SELECT p.* FROM scoped p WHERE NOT EXISTS (
            SELECT 1 FROM scoped newer WHERE newer.clip_id=p.clip_id
            AND newer.platform=p.platform AND newer.collected_at>p.collected_at
            )''', parameters).fetchall()
    results = []
    for row in rows:
        data = _observation_data(row)
        for key in ('campaign_accepted', 'campaign_rejected'):
            if data[key] is not None:
                data[key] = bool(data[key])
        results.append(ClipPerformance.model_validate(data))
    return results


def _content_keys(clip):
    """Identity evidence shared by copied exports and rerenders of a moment."""
    keys = []
    saved = clip.get('settings') or {}
    plan = saved.get('source_clip_plan') or {}
    source = clip.get('source_id') or (saved.get('source') or {}).get('id')
    start, duration = plan.get('start_seconds'), plan.get('duration_seconds')
    def valid(value):
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value))
    if (source and valid(start) and start >= 0 and valid(duration) and duration > 0
            and math.isfinite(start + duration)):
        keys.append(('window', source, start, duration))
    if clip.get('moment_id'):
        keys.append(('moment', clip['moment_id']))
    digest = str(clip.get('sha256') or '').casefold()
    if re.fullmatch('[0-9a-f]{64}', digest) and len(set(digest)) > 1:
        keys.append(('sha256', digest))
    return keys


def content_unit_ids(clips, *, settings=None):
    """Join hashes, moments and materially overlapping windows transitively.

    Source-grouped interval sweeps compare only currently overlapping windows;
    disjoint source windows are independent even when many records are supplied.
    """
    parents, owners, windows = {}, {}, {}
    threshold = (settings or load_settings()).dedup.timestamp_overlap_threshold

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for clip_id, clip in clips.items():
        keys = _content_keys(clip)
        if not keys:
            continue
        parents[clip_id] = clip_id
        for key in keys:
            if key in owners:
                left, right = root(clip_id), root(owners[key])
                parents[max(left, right)] = min(left, right)
            owners[key] = clip_id
            if key[0] == 'window':
                windows[key[1:]] = clip_id
    by_source = {}
    for (source, start, duration), clip_id in windows.items():
        by_source.setdefault(source, []).append((start, start + duration, duration, clip_id))
    for intervals in by_source.values():
        active, expirations = {}, []
        for start, end, duration, clip_id in sorted(intervals):
            while expirations and expirations[0][0] <= start:
                _, expired = heapq.heappop(expirations)
                active.pop(expired, None)
            for other, (other_end, other_duration) in active.items():
                left, right = root(clip_id), root(other)
                if left != right and (min(end, other_end) - start) / min(duration, other_duration) >= threshold:
                    parents[max(left, right)] = min(left, right)
            active[clip_id] = (end, duration)
            heapq.heappush(expirations, (end, clip_id))
    return {clip_id: root(clip_id) for clip_id in parents}


def independent_performance(observations, clips, *, settings=None):
    """Keep the latest representative of each evidenced independent content unit.

    Matching hashes OR materially overlapping source windows join a unit transitively.
    A clip ID alone cannot prove independence; unknown identities are omitted.
    Callers scope platform/style/niche before using the representatives.
    """
    observations = list(observations)
    identities = content_unit_ids({item.clip_id: clips.get(item.clip_id) or {} for item in observations},
                                  settings=settings)
    units = {}
    for observation in observations:
        identity = identities.get(observation.clip_id)
        if identity is None:
            continue
        previous = units.get(identity)
        if previous is None or (observation.collected_at, observation.clip_id) > (
                previous.collected_at, previous.clip_id):
            units[identity] = observation
    return list(units.values())
