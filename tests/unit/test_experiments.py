import pytest
import hashlib

from analytics.collectors import collect_performance
from analytics.experiments import add_variant, compare_variants, create_experiment
from analytics.models import ClipPerformance
from app.repositories.store import Store
from app.repositories.store import moment_identifier
import uuid
from test_analytics import MEASUREMENT_CONTEXT


def setup_experiment_store(tmp_path):
    store = Store(tmp_path / "test.db")
    order_id = str(uuid.uuid4())
    state = {"id": order_id, "status": "running", "stage": "test", "config": {},
             "source_selection": {"id": "source", "title": "Source", "url": "https://example.invalid"},
             "clip_entries": [{"source": {"id": "source", "title": "Source", "url": "https://example.invalid"},
                               "moment": {"clip_plan": {"start_seconds": 0, "duration_seconds": 30}},
                               "source_clip_plan": {"start_seconds": 0, "duration_seconds": 30}}]}
    store.save_order(state)
    with store.connection() as db:
        moment_id = db.execute("SELECT id FROM candidate_moments LIMIT 1").fetchone()["id"]
    return store, order_id, moment_id


def test_experiment_rejects_variants_with_more_than_two_changed_dimensions(tmp_path):
    store, order_id, moment_id = setup_experiment_store(tmp_path)
    store.save_clip({"id": "a", "order_id": order_id, "moment_id": moment_id,
                     "path": "clips/a.mp4", "sha256": "hash", "settings": {}})
    experiment = create_experiment(store, moment_id, "Hook test")
    with pytest.raises(ValueError, match="one or two"):
        add_variant(store, experiment, "a", "A", {"hook": "question", "cta": "follow", "duration": 30})


def test_comparison_reports_sample_qualified_outcomes(tmp_path):
    store, order_id, moment_id = setup_experiment_store(tmp_path)
    experiment = create_experiment(store, moment_id, "Caption test")
    for index, (label, style) in enumerate((("A", "studio"), ("A", "studio"),
                                             ("B", "colorized"), ("B", "colorized"))):
        clip_id = f"clip-{index}"
        store.save_clip({"id": clip_id, "order_id": order_id, "moment_id": moment_id,
                         "path": f"clips/{index}.mp4", "sha256": "hash", "caption_style": style,
                         "settings": {}})
        add_variant(store, experiment, clip_id, label, {"caption_style": style})
        collect_performance(store, ClipPerformance(clip_id=clip_id, platform="instagram", views=1000,
                           followers_gained=10 + index, completion_rate=.4 + index * .1,
                           measurement_context=MEASUREMENT_CONTEXT))

    report = compare_variants(store, experiment, minimum_samples=3)
    first = report["variants"][0]
    assert first["samples"]["clips"] == 2
    assert first["samples"]["independent_content_units"] == 1
    assert first["outcomes"]["followers_per_1000_views"] is None
    assert first["supported"] is False
    assert compare_variants(store, experiment, minimum_samples=2)["variants"][0]['supported'] is False
    supported = compare_variants(store, experiment, minimum_samples=1)["variants"][0]
    assert supported["supported"] is True
    assert supported["outcomes"]["followers_per_1000_views"] is not None
    assert report["dimensions"] == ["caption_style"]
    assert "causal" in report["note"]


def independent_outcome_fixture():
    """Different source windows and content hashes, without account access."""
    clips, observations = {}, []
    for index in range(5):
        identifier = f'clip-{index}'
        clips[identifier] = {'id': identifier, 'source_id': 'offline-source',
            'sha256': hashlib.sha256(identifier.encode()).hexdigest(), 'settings': {
                'source_clip_plan': {'start_seconds': index * 60, 'duration_seconds': 30}}}
        observations.append(ClipPerformance(clip_id=identifier, platform='youtube', views=1000,
            completion_rate=.9 if index == 0 else None,
            followers_generated=100 if index == 0 else None,
            measurement_context=MEASUREMENT_CONTEXT))
    return clips, observations


def test_variant_outcomes_require_support_for_each_metric():
    from analytics.experiments import _variant_outcomes
    clips, observations = independent_outcome_fixture()
    report = _variant_outcomes(observations, clips, minimum_samples=5)
    assert report['samples']['independent_content_units'] == 5
    assert report['samples']['completion_rate'] == report['samples']['follower_conversion'] == 1
    assert report['outcomes'] == {'completion_rate': None, 'followers_per_1000_views': None}
    assert report['supported'] is False


def test_variant_follower_ratio_excludes_unknown_numerators_and_nonpositive_views():
    from analytics.experiments import _variant_outcomes
    clips, observations = independent_outcome_fixture()
    observations[1] = observations[1].model_copy(update={'views': 0, 'followers_generated': 50})
    observations[2] = observations[2].model_copy(update={'views': None, 'followers_generated': 50})
    report = _variant_outcomes(observations, clips, minimum_samples=1)
    assert report['outcomes']['followers_per_1000_views'] == 100
    assert report['samples']['follower_conversion'] == 1
    assert report['outcomes']['completion_rate'] == .9


def test_variant_outcomes_suppress_mixed_platform_comparisons():
    from analytics.experiments import _variant_outcomes
    clips, observations = independent_outcome_fixture()
    observations[1] = observations[1].model_copy(update={
        'platform': 'tiktok', 'completion_rate': .1, 'followers_generated': 1})
    report = _variant_outcomes(observations, clips, minimum_samples=1)
    assert report['supported'] is False
    assert report['reason'] == 'mixed_platforms'
    assert all(value is None for value in report['outcomes'].values())


def block_experiment_store(tmp_path, *, scope='content_blocks', spacing=60):
    store = Store(tmp_path / 'blocks.db')
    order_id = str(uuid.uuid4())
    source = {'id': 'offline-source', 'title': 'Synthetic source', 'url': 'https://example.invalid'}
    plans = [{'start_seconds': index * spacing, 'duration_seconds': 30} for index in range(4)]
    store.save_order({'id': order_id, 'status': 'running', 'stage': 'test', 'config': {},
                      'clip_entries': [{'source': source, 'source_clip_plan': plan} for plan in plans]})
    moments = [moment_identifier(order_id, source['id'], plan) for plan in plans]
    experiment = create_experiment(store, moments[0], 'Matched caption variants', scope=scope)
    return store, order_id, experiment, moments


def add_block_clip(store, order_id, experiment, moment_id, block, variant, *, copy=0,
                   completion=.8, followers=10, views=1000, context=MEASUREMENT_CONTEXT):
    clip_id = f'{block}-{variant}-{copy}'
    # Identity and source windows come from actual persisted moments, not fabricated settings.
    store.save_clip({'id': clip_id, 'order_id': order_id, 'moment_id': moment_id,
        'path': f'clips/{clip_id}.mp4',
        'sha256': hashlib.sha256(f'{block}:{variant}'.encode()).hexdigest(), 'settings': {}})
    add_variant(store, experiment, clip_id, variant, {'caption_style': variant})
    collect_performance(store, ClipPerformance(clip_id=clip_id, platform='youtube', views=views,
        followers_generated=followers, completion_rate=completion, measurement_context=context))
    return clip_id


def test_content_block_scope_accepts_distinct_persisted_moments(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    add_block_clip(store, order_id, experiment, moments[0], 0, 'A')
    add_block_clip(store, order_id, experiment, moments[1], 1, 'A')
    with store.connection() as db:
        assert db.execute('SELECT scope FROM experiments WHERE id=?', (experiment,)).fetchone()[0] == 'content_blocks'


def test_default_single_moment_scope_still_rejects_other_source_moments(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path, scope='single_moment')
    with pytest.raises(ValueError, match='source moment'):
        add_block_clip(store, order_id, experiment, moments[1], 1, 'A')


def test_experiment_scope_rejects_unknown_values(tmp_path):
    store, _, moment = setup_experiment_store(tmp_path)
    with pytest.raises(ValueError, match='scope'):
        create_experiment(store, moment, 'Invalid scope', scope='pooled')


def test_scope_migration_preserves_existing_experiments_and_measurements(tmp_path):
    import sqlite3
    from contextlib import closing
    store, order_id, moment = setup_experiment_store(tmp_path)
    experiment = create_experiment(store, moment, 'Existing experiment')
    store.save_clip({'id': 'legacy-clip', 'order_id': order_id, 'moment_id': moment,
                     'path': 'clip.mp4', 'sha256': 'hash', 'settings': {}})
    collect_performance(store, ClipPerformance(clip_id='legacy-clip', platform='youtube', views=123,
                                             measurement_context=MEASUREMENT_CONTEXT))
    with store.connection(write=True) as db:
        columns = {row['name'] for row in db.execute('PRAGMA table_info(experiments)')}
        if 'scope' in columns:
            db.execute('ALTER TABLE experiments DROP COLUMN scope')
        db.execute('DELETE FROM schema_migrations WHERE version=10')
    migrated = Store(store.path)
    with migrated.connection() as db:
        assert db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] == 10
        row = db.execute('SELECT * FROM experiments WHERE id=?', (experiment,)).fetchone()
        assert row['scope'] == 'single_moment' and row['source_moment_id'] == moment
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    from analytics.collectors import latest_performance
    assert latest_performance(migrated)[0].measurement_context.model_dump() == MEASUREMENT_CONTEXT
    with closing(sqlite3.connect(store.path.with_suffix('.db.before-v10.bak'))) as backup:
        assert backup.execute('SELECT source_moment_id FROM experiments').fetchone()[0] == moment
        assert backup.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] == 9
        assert backup.execute('SELECT views FROM performance_metrics').fetchone()[0] == 123


def test_matched_variants_reach_support_from_three_distinct_content_blocks(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    for block in range(3):
        for variant in ('A', 'B'):
            add_block_clip(store, order_id, experiment, moments[block], block, variant)
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['scope'] == 'content_blocks' and report['supported'] is True
    assert report['block_coverage']['complete_blocks'] == 3
    assert report['block_coverage']['completion_rate_blocks'] == 3
    assert report['block_coverage']['follower_conversion_blocks'] == 3
    assert all(variant['samples']['independent_content_units'] == 3 for variant in report['variants'])
    assert all(variant['outcomes']['followers_per_1000_views'] == 10 for variant in report['variants'])
    assert 'causal' in report['note']


def test_copied_exports_of_one_block_cannot_fill_replication_minimum(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    for copy in range(3):
        for variant in ('A', 'B'):
            add_block_clip(store, order_id, experiment, moments[0], 0, variant, copy=copy)
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['supported'] is False
    assert report['block_coverage']['complete_blocks'] == 1
    assert all(variant['samples']['completion_rate'] == 1 for variant in report['variants'])


def test_missing_variant_block_cannot_fill_the_paired_minimum(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    for block in range(3):
        for variant in ('A', 'B'):
            if block != 2 or variant != 'B':
                add_block_clip(store, order_id, experiment, moments[block], block, variant)
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['supported'] is False
    assert report['block_coverage']['complete_blocks'] == 2
    assert [block['missing_variants'] for block in report['block_coverage']['blocks'] if block['missing_variants']] == [['B']]
    assert all(variant['samples']['completion_rate'] == 2 for variant in report['variants'])


def test_incomplete_extra_block_cannot_change_supported_comparison_outcomes(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    for block in range(3):
        for variant in ('A', 'B'):
            add_block_clip(store, order_id, experiment, moments[block], block, variant)
    add_block_clip(store, order_id, experiment, moments[3], 3, 'A', views=1, followers=1000,
                   context={**MEASUREMENT_CONTEXT, 'account_id': 'different-account'})
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['supported'] is True
    assert report['block_coverage']['registered_blocks'] == 4
    assert report['block_coverage']['complete_blocks'] == 3
    assert all(variant['outcomes']['followers_per_1000_views'] == 10 for variant in report['variants'])


def test_content_block_outcomes_require_metric_pairs_for_every_variant(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    for block in range(3):
        for variant in ('A', 'B'):
            followers = None if block == 2 and variant == 'B' else 1000 if block == 2 else 10
            add_block_clip(store, order_id, experiment, moments[block], block, variant, followers=followers)
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['block_coverage']['completion_rate_blocks'] == 3
    assert report['block_coverage']['follower_conversion_blocks'] == 2
    for variant in report['variants']:
        assert variant['outcome_support']['completion_rate'] is True
        assert variant['outcome_support']['followers_per_1000_views'] is False
        assert variant['outcomes']['followers_per_1000_views'] is None
    lower_floor = compare_variants(store, experiment, minimum_samples=2)
    assert all(variant['outcomes']['followers_per_1000_views'] == 10 for variant in lower_floor['variants'])


def test_matched_content_blocks_cannot_pool_different_measurement_contexts(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    for block in range(3):
        for variant in ('A', 'B'):
            context = {**MEASUREMENT_CONTEXT, 'account_id': 'other'} if block == 2 and variant == 'B' else MEASUREMENT_CONTEXT
            add_block_clip(store, order_id, experiment, moments[block], block, variant, context=context)
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['supported'] is False and report['reason'] == 'mixed_measurement_contexts'
    assert all(value is None for variant in report['variants'] for value in variant['outcomes'].values())


def test_one_variant_cannot_establish_a_content_block_comparison(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    for block in range(3):
        add_block_clip(store, order_id, experiment, moments[block], block, 'A')
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['supported'] is False and report['reason'] == 'comparison_variants_required'


def test_different_moment_ids_for_the_same_source_window_are_one_content_block(tmp_path):
    store, _, experiment, _ = block_experiment_store(tmp_path)
    source = {'id': 'offline-source', 'title': 'Synthetic source', 'url': 'https://example.invalid'}
    plan = {'start_seconds': 0, 'duration_seconds': 30}
    for copy in range(3):
        order_id = str(uuid.uuid4())
        store.save_order({'id': order_id, 'status': 'running', 'stage': 'test', 'config': {},
                          'clip_entries': [{'source': source, 'source_clip_plan': plan}]})
        moment = moment_identifier(order_id, source['id'], plan)
        for variant in ('A', 'B'):
            add_block_clip(store, order_id, experiment, moment, copy, variant)
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['block_coverage']['complete_blocks'] == 1
    assert report['supported'] is False


@pytest.mark.parametrize('views', [None, 0])
def test_content_block_metric_pairs_need_positive_known_views_on_both_variants(tmp_path, views):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    for block in range(3):
        for variant in ('A', 'B'):
            add_block_clip(store, order_id, experiment, moments[block], block, variant,
                           views=views if block == 2 and variant == 'B' else 1000)
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['block_coverage']['completion_rate_blocks'] == 2
    assert report['block_coverage']['follower_conversion_blocks'] == 2
    assert report['supported'] is False


def test_content_block_registration_rejects_invalid_moments_and_changed_replicate_settings(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path)
    with store.connection(write=True) as db:
        db.execute('UPDATE candidate_moments SET start_seconds=-1 WHERE id=?', (moments[1],))
    with pytest.raises(ValueError, match='valid persisted source moment'):
        add_block_clip(store, order_id, experiment, moments[1], 1, 'A')
    add_block_clip(store, order_id, experiment, moments[0], 0, 'A')
    store.save_clip({'id': 'changed', 'order_id': order_id, 'moment_id': moments[2],
                     'path': 'changed.mp4', 'sha256': 'hash', 'settings': {}})
    with pytest.raises(ValueError, match='identical settings'):
        add_variant(store, experiment, 'changed', 'A', {'caption_style': 'different'})
    with pytest.raises(ValueError, match='one or two'):
        add_variant(store, experiment, 'changed', 'B', {'duration': 30, 'hook': 'question'})


def test_comparison_rejects_a_boolean_sample_minimum(tmp_path):
    store, _, experiment, _ = block_experiment_store(tmp_path)
    with pytest.raises(ValueError, match='positive integer'):
        compare_variants(store, experiment, minimum_samples=True)


def test_shifted_overlapping_moments_cannot_supply_independent_content_blocks(tmp_path):
    store, order_id, experiment, moments = block_experiment_store(tmp_path, spacing=1)
    for block in range(3):
        for variant in ('A', 'B'):
            add_block_clip(store, order_id, experiment, moments[block], block, variant)
    report = compare_variants(store, experiment, minimum_samples=3)
    assert report['supported'] is False
    assert report['block_coverage']['complete_blocks'] == 1


def test_content_identity_joins_transitive_overlaps_using_the_configured_threshold():
    from analytics.collectors import content_unit_ids
    from app.core.config import load_settings
    clips = {str(index): {'source_id': 'source', 'settings': {'source_clip_plan': {
        'start_seconds': index * 10, 'duration_seconds': 30}}} for index in range(3)}
    settings = load_settings(environ={})
    assert len(set(content_unit_ids(clips, settings=settings).values())) == 1
    stricter = settings.model_copy(update={'dedup': settings.dedup.model_copy(update={
        'timestamp_overlap_threshold': .75})})
    assert len(set(content_unit_ids(clips, settings=stricter).values())) == 3
    for index, clip in enumerate(clips.values()):
        clip['settings']['source_clip_plan']['start_seconds'] = index * 60
    assert len(set(content_unit_ids(clips, settings=settings).values())) == 3
