"""Local, descriptive comparisons of explicitly imported audience observations.

``create_experiment(store, seed_moment_id, name)`` preserves the single-moment
default: rerenders of one moment cannot supply independent replication.
Opt in with ``scope='content_blocks'`` to register the same variant settings
across distinct persisted moments using ``add_variant``. ``compare_variants``
then uses only content blocks covered by every registered variant, with a
separate paired positive-view sample minimum for each outcome. Its coverage
report names missing variants. Complete account/window/view-definition context
and platform must agree. These observed associations do not establish causal
uplift, and this interface never publishes posts or creates observations.
"""

import json
import math
import uuid
from statistics import mean

from analytics.collectors import content_unit_ids, independent_performance, latest_performance
from app.repositories.database import timestamp
from app.repositories.store import encode


def create_experiment(store, source_moment_id, name, *, scope='single_moment'):
    """Create a descriptive single-moment study or an opt-in matched content study."""
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 300:
        raise ValueError('Experiment needs a bounded name')
    if scope not in ('single_moment', 'content_blocks'):
        raise ValueError('Experiment scope must be single_moment or content_blocks')
    identifier = str(uuid.uuid4())
    with store.connection(write=True) as db:
        db.execute('INSERT INTO experiments (id,source_moment_id,name,created_at,scope) VALUES (?,?,?,?,?)',
                   (identifier, source_moment_id, name.strip(), timestamp(), scope))
    return identifier


def add_variant(store, experiment_id, clip_id, variant, settings):
    """Record one variant; content blocks require a valid persisted source moment."""
    if not isinstance(variant, str) or not 1 <= len(variant) <= 80 or not isinstance(settings, dict):
        raise ValueError('Variant needs a label and recorded settings')
    if not 1 <= len(settings) <= 2 or any(not isinstance(key, str) or not key for key in settings):
        raise ValueError('An experiment variant must change one or two named dimensions')
    with store.connection(write=True) as db:
        experiment = db.execute('SELECT source_moment_id,scope FROM experiments WHERE id=?', (experiment_id,)).fetchone()
        clip = db.execute('''SELECT c.moment_id,m.source_id,m.start_seconds,m.duration_seconds
            FROM clips c LEFT JOIN candidate_moments m ON m.id=c.moment_id WHERE c.id=?''', (clip_id,)).fetchone()
        if experiment is None or clip is None:
            raise ValueError('Variant needs an existing experiment and clip')
        if experiment['scope'] == 'single_moment' and experiment['source_moment_id'] != clip['moment_id']:
            raise ValueError('Variant must belong to the experiment source moment')
        if experiment['scope'] == 'content_blocks' and not _valid_moment(clip):
            raise ValueError('Content-block variants need a valid persisted source moment')
        existing = db.execute('SELECT settings FROM experiment_variants WHERE experiment_id=?',
                              (experiment_id,)).fetchall()
        dimensions = set(settings)
        for row in existing:
            dimensions.update(json.loads(row['settings']))
        if len(dimensions) > 2:
            raise ValueError('An experiment may compare only one or two changed dimensions')
        same_variant = db.execute('SELECT settings FROM experiment_variants WHERE experiment_id=? AND variant=?',
                                  (experiment_id, variant)).fetchall()
        if same_variant and any(json.loads(row['settings']) != settings for row in same_variant):
            raise ValueError('Replicates of a variant must use identical settings')
        db.execute('INSERT INTO experiment_variants VALUES (?,?,?,?,?)',
                   (str(uuid.uuid4()), experiment_id, clip_id, variant, encode(settings)))


def _valid_moment(moment):
    return bool(moment['source_id'] and all(not isinstance(moment[key], bool)
        and isinstance(moment[key], (int, float)) and math.isfinite(moment[key])
        for key in ('start_seconds', 'duration_seconds'))
        and moment['start_seconds'] >= 0 and moment['duration_seconds'] > 0)


def _comparison_scope(items):
    if len({item.platform for item in items}) > 1:
        return None, 'mixed_platforms'
    contexts = [item.measurement_context for item in items]
    if not contexts or any(context is None or context.cohort_key is None for context in contexts):
        return None, 'measurement_context_required'
    if len({context.cohort_key for context in contexts}) > 1:
        return None, 'mixed_measurement_contexts'
    return contexts[0].model_dump(), None


def _variant_outcomes(items, clips, *, minimum_samples, completion_items=None, follower_items=None):
    """Support each outcome with its own independent, comparable observations."""
    platforms = {item.platform for item in items}
    context, context_reason = _comparison_scope(items)
    independent = independent_performance(items, clips)
    completion = independent_performance([item for item in items
        if item.views is not None and item.views > 0 and item.completion_rate is not None], clips)
    followers = independent_performance([item for item in items
        if item.views is not None and item.views > 0 and item.followers_generated is not None], clips)
    if completion_items is not None:
        completion = independent_performance(completion_items, clips)
    if follower_items is not None:
        followers = independent_performance(follower_items, clips)
    comparable = context_reason is None
    support = {'completion_rate': comparable and len(completion) >= minimum_samples,
               'followers_per_1000_views': comparable and len(followers) >= minimum_samples}
    supported = any(support.values())
    follower_views = sum(item.views for item in followers)
    return {'samples': {'clips': len({item.clip_id for item in items}), 'observations': len(items),
                'independent_content_units': len(independent),
                'views': sum(item.views or 0 for item in independent),
                'completion_rate': len(completion), 'follower_conversion': len(followers),
                'follower_conversion_views': follower_views},
            'outcomes': {
                'completion_rate': round(mean(item.completion_rate for item in completion), 4)
                    if support['completion_rate'] else None,
                'followers_per_1000_views': round(sum(item.followers_generated for item in followers)
                    * 1000 / follower_views, 4) if support['followers_per_1000_views'] else None},
            'outcome_support': support, 'supported': supported,
            'platform': next(iter(platforms)) if len(platforms) == 1 else None,
            'measurement_context': context,
            'reason': context_reason or ('insufficient_metric_samples' if not supported else None)}


def _matched_blocks(rows, observations, clips):
    labels = sorted({row['variant'] for row in rows})
    identities = content_unit_ids(clips)
    blocks = {}
    for row in rows:
        identity = identities.get(row['clip_id'])
        if identity is not None:
            blocks.setdefault(identity, {}).setdefault(row['variant'], []).append(row['clip_id'])
    complete = {identity: group for identity, group in blocks.items() if set(group) == set(labels)}
    items = {label: [] for label in labels}
    paired = {metric: {label: [] for label in labels} for metric in ('completion_rate', 'followers_generated')}
    observations_by_clip = {}
    for observation in observations:
        observations_by_clip.setdefault(observation.clip_id, []).append(observation)
    coverage = []
    for identity, group in sorted(blocks.items()):
        by_variant = {label: [item for clip_id in clip_ids for item in observations_by_clip.get(clip_id, [])]
                      for label, clip_ids in group.items()}
        coverage.append({'block_id': identity, 'clip_ids_by_variant': group,
            'present_variants': sorted(group), 'missing_variants': sorted(set(labels) - set(group)),
            'missing_observed_variants': [label for label in labels if not by_variant.get(label)]})
        if identity not in complete:
            continue
        for label in labels:
            items[label].extend(by_variant[label])
        for metric in paired:
            matches = {}
            for label in labels:
                valid = [item for item in by_variant[label] if item.views is not None
                         and item.views > 0 and getattr(item, metric) is not None]
                if valid:
                    matches[label] = max(valid, key=lambda item: (item.collected_at, item.clip_id))
            if len(matches) == len(labels):
                for label, observation in matches.items():
                    paired[metric][label].append(observation)
    return items, paired, {'registered_blocks': len(blocks), 'complete_blocks': len(complete),
        'required_variants': labels, 'blocks': coverage,
        'completion_rate_blocks': len(paired['completion_rate'][labels[0]]) if labels else 0,
        'follower_conversion_blocks': len(paired['followers_generated'][labels[0]]) if labels else 0}


def compare_variants(store, experiment_id, *, minimum_samples=3, as_of=None):
    """Compare known outcomes with independent, scope-specific sample support."""
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
        raise ValueError('minimum_samples must be a positive integer')
    observations = latest_performance(store, as_of=as_of)
    clips = {clip['id']: clip for clip in store.list_clips()}
    with store.connection() as db:
        experiment = db.execute('SELECT scope FROM experiments WHERE id=?', (experiment_id,)).fetchone()
        if experiment is None:
            raise KeyError('Experiment not found')
        rows = db.execute('SELECT * FROM experiment_variants WHERE experiment_id=?', (experiment_id,)).fetchall()
        moments = db.execute('''SELECT c.id,m.source_id,m.start_seconds,m.duration_seconds
            FROM clips c JOIN candidate_moments m ON m.id=c.moment_id
            JOIN experiment_variants v ON v.clip_id=c.id WHERE v.experiment_id=?''', (experiment_id,)).fetchall()
    scope = experiment['scope']
    participating_clips = {row['clip_id'] for row in rows}
    clips = {identifier: clip for identifier, clip in clips.items() if identifier in participating_clips}
    for moment in moments:
        if _valid_moment(moment):
            clip = clips[moment['id']]
            clip['source_id'] = moment['source_id']
            clip['settings'] = {**clip['settings'], 'source_clip_plan': {
                'start_seconds': moment['start_seconds'], 'duration_seconds': moment['duration_seconds']}}
    block_coverage = None
    if scope == 'content_blocks':
        valid_ids = {moment['id'] for moment in moments if _valid_moment(moment)}
        clips = {identifier: clip for identifier, clip in clips.items() if identifier in valid_ids}
        matched, paired, block_coverage = _matched_blocks(rows, observations, clips)
        compared_items = [item for items in matched.values() for item in items]
    else:
        compared_items = [item for item in observations if item.clip_id in participating_clips]
    context, comparison_reason = _comparison_scope(compared_items)
    if scope == 'content_blocks' and len(block_coverage['required_variants']) < 2:
        comparison_reason = 'comparison_variants_required'
    variants = []
    all_dimensions = set()
    groups = {}
    for row in rows:
        groups.setdefault(row['variant'], []).append(row)
    for variant, group in groups.items():
        settings = json.loads(group[0]['settings'])
        all_dimensions.update(settings)
        clip_ids = {row['clip_id'] for row in group}
        items = [item for item in observations if item.clip_id in clip_ids]
        if scope == 'content_blocks':
            outcomes = _variant_outcomes(matched[variant], clips, minimum_samples=minimum_samples,
                completion_items=paired['completion_rate'][variant],
                follower_items=paired['followers_generated'][variant])
        else:
            outcomes = _variant_outcomes(items, clips, minimum_samples=minimum_samples)
        if comparison_reason:
            outcomes.update(supported=False, reason=comparison_reason,
                            outcomes={key: None for key in outcomes['outcomes']},
                            outcome_support={key: False for key in outcomes['outcome_support']})
        variants.append({
            'variant': variant, 'clip_ids': sorted(clip_ids), 'settings': settings,
            'performance': [item.model_dump(mode='json') for item in items],
            **outcomes,
        })
    supported_metrics = [metric for metric in ('completion_rate', 'followers_per_1000_views')
                         if variants and all(variant['outcome_support'][metric] for variant in variants)]
    if scope == 'content_blocks' and not supported_metrics and comparison_reason is None:
        comparison_reason = 'insufficient_paired_metric_samples'
    return {'experiment_id': experiment_id, 'variants': variants, 'dimensions': sorted(all_dimensions),
        'scope': scope, 'block_coverage': block_coverage,
        'supported': bool(supported_metrics), 'supported_metrics': supported_metrics,
        'minimum_samples': minimum_samples, 'measurement_context': context, 'reason': comparison_reason,
        'note': 'Observed outcomes only. Materially overlapping content windows or matching hashes count once; unknown identities '
                'do not establish independent support. Each metric requires its own known positive-view '
                'samples in one platform and one explicit account/window/view-definition context across all '
                'variants. Content-block comparisons exclude unmatched blocks and require known metric '
                'pairs across every variant. These observed associations do not establish causal uplift.'}
