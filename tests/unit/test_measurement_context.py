"""Offline contracts for comparable manually imported audience observations."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
import httpx

from analytics.collectors import collect_performance, latest_performance
from analytics.models import ClipPerformance
from app.repositories.store import Store
from test_publishing import prepared
from test_analytics import feedback_samples, MEASUREMENT_CONTEXT as CONTEXT


def test_rewatch_metrics_roundtrip_without_becoming_completion_or_retention(tmp_path):
    store, _, _ = prepared(tmp_path)
    observation = ClipPerformance(clip_id='clip', platform='youtube', views=100,
        measurement_context=CONTEXT, average_view_percentage=135.5, audience_watch_ratio=1.7)
    identifier = collect_performance(store, observation)
    assert collect_performance(store, observation.model_dump(mode='json')) == identifier
    observed = latest_performance(store)[0]
    assert observed.measurement_context.model_dump() == CONTEXT
    assert observed.average_view_percentage == 135.5 and observed.audience_watch_ratio == 1.7
    assert observed.completion_rate is None and observed.retention is None
    with store.connection() as db:
        saved = db.execute('SELECT measurement_context FROM performance_metrics').fetchone()[0]
    assert json.loads(saved) == CONTEXT
    changed = observation.model_dump(mode='json')
    changed['measurement_context']['account_id'] = 'another-channel'
    with pytest.raises(ValueError, match='different metrics'):
        collect_performance(store, changed)


@pytest.mark.parametrize('field,value', [
    ('average_view_percentage', -1.0), ('audience_watch_ratio', -0.1),
    ('average_view_percentage', float('inf')), ('audience_watch_ratio', float('nan'))])
def test_rewatch_metrics_reject_invalid_values(field, value):
    with pytest.raises(ValueError):
        ClipPerformance(clip_id='clip', platform='youtube', **{field: value})


@pytest.mark.parametrize('changes', [
    {'account_id': ''}, {'reporting_window_hours': 0},
    {'reporting_window_hours': float('inf')}, {'view_definition': 'guessed'},
    {'definition_version': 'x' * 201}])
def test_measurement_context_refuses_invalid_metadata(changes):
    with pytest.raises(ValueError):
        ClipPerformance(clip_id='clip', platform='youtube', measurement_context={**CONTEXT, **changes})


def test_v9_migration_preserves_legacy_observations_with_unknown_context(tmp_path):
    store, _, _ = prepared(tmp_path)
    collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', views=123))
    with store.connection(write=True) as db:
        columns = {row['name'] for row in db.execute('PRAGMA table_info(performance_metrics)')}
        for column in ('measurement_context', 'average_view_percentage', 'audience_watch_ratio'):
            if column in columns:
                db.execute(f'ALTER TABLE performance_metrics DROP COLUMN {column}')
        if 'scope' in {row['name'] for row in db.execute('PRAGMA table_info(experiments)')}:
            db.execute('ALTER TABLE experiments DROP COLUMN scope')
        db.execute('DELETE FROM schema_migrations WHERE version>=9')
    migrated = Store(store.path)
    with migrated.connection() as db:
        assert db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] == 10
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    observation = latest_performance(migrated)[0]
    assert observation.views == 123 and observation.measurement_context is None
    assert observation.average_view_percentage is None and observation.audience_watch_ratio is None
    backup = store.path.with_suffix('.db.before-v9.bak')
    with closing(sqlite3.connect(backup)) as db:
        assert db.execute('SELECT views FROM performance_metrics').fetchone()[0] == 123
        assert db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] == 8
    assert Store(store.path).path == migrated.path


def test_unknown_learning_context_cannot_adjust_a_candidate(tmp_path):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', completion=.9)
    feedback_samples(store, path, 'comparison', duration=45, question=False, completion=.1)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35,
                                 opening_question=True, niche='business', platform='youtube')
    assert report['supported'] is False and report['adjustment'] == 0
    assert report['reason'] == 'learning_context_required'


@pytest.mark.parametrize('change', [
    {'account_id': 'other-account'}, {'reporting_window_hours': 168.0},
    {'view_definition': 'play_starts'}, {'definition_version': 'another-version'}])
def test_feedback_cannot_pool_other_accounts_horizons_or_definitions(tmp_path, change):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', count=4, completion=.9)
    feedback_samples(store, path, 'comparison', count=4, duration=45, question=False, completion=.1)
    feedback_samples(store, path, 'foreign-target', completion=.9,
                     measurement_context={**CONTEXT, **change})
    feedback_samples(store, path, 'foreign-comparison', duration=45, question=False, completion=.1,
                     measurement_context={**CONTEXT, **change})
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35,
        opening_question=True, niche='business', platform='youtube', measurement_context=CONTEXT)
    assert report['samples'] == report['comparison_samples'] == 4
    assert report['supported'] is False and report['adjustment'] == 0


def test_complete_explicit_context_allows_supported_feedback(tmp_path):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', completion=.9)
    feedback_samples(store, path, 'comparison', duration=45, question=False, completion=.1)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35,
        opening_question=True, niche='business', platform='youtube', measurement_context=CONTEXT)
    assert report['supported'] is True and report['adjustment'] > 0
    assert report['cohort']['measurement_context'] == CONTEXT


def test_context_filter_keeps_the_latest_matching_snapshot_not_a_newer_other_account(tmp_path):
    store, _, _ = prepared(tmp_path)
    now = datetime.now(timezone.utc)
    for minutes, views, context in ((-3, 100, CONTEXT),
            (-2, 900, {**CONTEXT, 'account_id': 'other-account'}), (30, 2000, CONTEXT)):
        collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', views=views,
            collected_at=(now + timedelta(minutes=minutes)).isoformat(), measurement_context=context))
    observed = latest_performance(store, measurement_context=CONTEXT)
    assert len(observed) == 1 and observed[0].views == 100


@pytest.mark.parametrize('context', [None, {}, {**CONTEXT, 'view_definition': 'unknown'}])
def test_incomplete_observation_context_does_not_establish_learning_support(tmp_path, context):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', measurement_context=context)
    feedback_samples(store, path, 'comparison', duration=45, question=False, measurement_context=context)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35,
        opening_question=True, niche='business', platform='youtube', measurement_context=CONTEXT)
    assert report['samples'] == report['comparison_samples'] == 0
    assert report['adjustment'] == 0 and report['supported'] is False


@pytest.mark.parametrize('change', [
    {'account_id': 'another-account'}, {'reporting_window_hours': 168.0},
    {'view_definition': 'play_starts'}, {'definition_version': 'another-version'}, None])
def test_experiment_variants_cannot_compare_different_or_unknown_contexts(tmp_path, change):
    from analytics.experiments import add_variant, compare_variants, create_experiment
    from test_experiments import setup_experiment_store
    store, order_id, moment_id = setup_experiment_store(tmp_path)
    experiment = create_experiment(store, moment_id, 'Comparable measurements')
    for label, context in (('A', CONTEXT), ('B', {**CONTEXT, **change} if change else None)):
        store.save_clip({'id': label, 'order_id': order_id, 'moment_id': moment_id,
                         'path': f'{label}.mp4', 'sha256': 'hash', 'settings': {}})
        add_variant(store, experiment, label, label, {'caption_style': label})
        collect_performance(store, ClipPerformance(clip_id=label, platform='youtube', views=1000,
            followers_generated=10, completion_rate=.9, measurement_context=context))
    report = compare_variants(store, experiment, minimum_samples=1)
    assert all(variant['supported'] is False for variant in report['variants'])
    assert all(value is None for variant in report['variants'] for value in variant['outcomes'].values())
    assert report['reason'] in {'mixed_measurement_contexts', 'measurement_context_required'}


def test_cli_metrics_import_preserves_context_and_distinct_rewatch_metrics(tmp_path, capsys):
    from clipping.cli import main
    store, _, _ = prepared(tmp_path)
    observation = ClipPerformance(clip_id='clip', platform='youtube', views=100,
        measurement_context=CONTEXT, average_view_percentage=140.0, audience_watch_ratio=1.6)
    source = tmp_path / 'manual-observation.json'
    source.write_text(observation.model_dump_json(), encoding='utf-8')
    for _ in range(2):
        assert main(['metrics', 'import', str(source), '--storage', str(tmp_path)]) == 0
        assert json.loads(capsys.readouterr().out)['measured_clips'] == 1
    saved = latest_performance(store)
    assert len(saved) == 1 and saved[0].measurement_context.model_dump() == CONTEXT
    assert saved[0].average_view_percentage == 140.0 and saved[0].audience_watch_ratio == 1.6


@pytest.mark.asyncio
async def test_typed_metrics_api_preserves_context_and_rewatch_metrics(tmp_path):
    from fastapi import FastAPI
    from app.api.routes import router
    store, _, _ = prepared(tmp_path)
    application = FastAPI()
    application.state.domain_store = store
    application.include_router(router)
    observation = ClipPerformance(clip_id='clip', platform='youtube', views=100,
        measurement_context=CONTEXT, average_view_percentage=145.0, audience_watch_ratio=1.8)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                base_url='http://testserver') as client:
        first = await client.post('/metrics', json=observation.model_dump(mode='json'))
        repeated = await client.post('/metrics', json=observation.model_dump(mode='json'))
    assert first.status_code == repeated.status_code == 201
    assert first.json() == repeated.json()
    saved = latest_performance(store)[0]
    assert saved.measurement_context.model_dump() == CONTEXT
    assert saved.average_view_percentage == 145.0 and saved.audience_watch_ratio == 1.8
    assert saved.completion_rate is None and saved.retention is None
