from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from test_publishing import prepared

MEASUREMENT_CONTEXT = {'account_id': 'owned-channel', 'reporting_window_hours': 24.0,
                       'view_definition': 'engaged_views', 'definition_version': '2026-08-24'}


def test_metrics_persist_unknowns_and_refuse_invalid_values(tmp_path):
    from analytics.models import ClipPerformance
    from analytics.collectors import collect_performance, latest_performance
    store, _, _ = prepared(tmp_path)
    observation = ClipPerformance(clip_id='clip', platform='youtube', views=100, likes=5,
                                  completion_rate=.8, reward_amount='1.25')
    collect_performance(store, observation)
    assert latest_performance(store)[0].saves is None
    assert str(latest_performance(store)[0].reward_amount) == '1.25'
    assert latest_performance(store)[0].hashtags is None
    with pytest.raises(ValueError):
        ClipPerformance(clip_id='clip', platform='youtube', completion_rate=1.5)
    with pytest.raises(ValueError):
        ClipPerformance(clip_id='clip', platform='youtube', views=-1)
    with pytest.raises(ValueError):
        ClipPerformance(clip_id='clip', platform='youtube', hashtags=['#valid', 'bad tag'])


def test_observation_retry_is_idempotent_with_observed_hashtags(tmp_path):
    from analytics.collectors import collect_performance, latest_performance
    from analytics.models import ClipPerformance
    store, _, _ = prepared(tmp_path)
    observation = ClipPerformance(clip_id='clip', platform='youtube', views=100,
        hashtags=['#Education', '#Business'], campaign_accepted=True, reward_amount='1.25')
    identifier = collect_performance(store, observation)
    assert collect_performance(store, observation.model_dump(mode='json')) == identifier
    assert len(latest_performance(store)) == 1
    with pytest.raises(ValueError, match='different metrics'):
        collect_performance(store, observation.model_copy(update={'hashtags': ['#Different']}))


def test_latest_observations_exclude_future_snapshots_without_losing_earlier_data(tmp_path):
    from analytics.collectors import collect_performance, latest_performance
    from analytics.models import ClipPerformance
    store, _, _ = prepared(tmp_path)
    now = datetime.now(timezone.utc)
    for offset, views in ((-2, 100), (-1, 200), (365, 999)):
        collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', views=views,
            collected_at=(now + timedelta(days=offset)).isoformat()))
    assert latest_performance(store)[0].views == 200
    assert latest_performance(store, as_of=now - timedelta(days=1, hours=12))[0].views == 100
    assert latest_performance(store, as_of=now - timedelta(days=3)) == []


def test_latest_observations_require_an_aware_cutoff(tmp_path):
    from analytics.collectors import latest_performance
    store, _, _ = prepared(tmp_path)
    with pytest.raises(ValueError, match='timezone'):
        latest_performance(store, as_of=datetime(2026, 10, 22))


def test_hashtag_schema_migration_preserves_old_observations_as_unknown(tmp_path):
    from analytics.collectors import collect_performance, latest_performance
    from analytics.models import ClipPerformance
    from app.repositories.store import Store
    store, _, _ = prepared(tmp_path)
    collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', views=10))
    with store.connection(write=True) as db:
        db.execute('ALTER TABLE performance_metrics DROP COLUMN cta_used')
        db.execute('ALTER TABLE performance_metrics DROP COLUMN hashtags')
        for column in ('measurement_context', 'average_view_percentage', 'audience_watch_ratio'):
            db.execute(f'ALTER TABLE performance_metrics DROP COLUMN {column}')
        db.execute('ALTER TABLE experiments DROP COLUMN scope')
        db.execute('DELETE FROM schema_migrations WHERE version>=7')

    migrated = Store(store.path)

    assert latest_performance(migrated)[0].hashtags is None
    with migrated.connection() as db:
        assert db.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] == 10


def test_follower_conversion_is_view_weighted_and_keeps_unknowns_null(tmp_path):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from analytics.reports import business_metrics
    store, _, path = prepared(tmp_path)
    store.save_clip({**store.get_clip('clip'), 'id': 'clip-b', 'path': str(path)})
    collect_performance(store, ClipPerformance(clip_id='clip', platform='instagram', views=100_000,
        profile_visits=900, followers_generated=200))
    collect_performance(store, ClipPerformance(clip_id='clip-b', platform='instagram', views=20_000,
        profile_visits=1200, followers_generated=500))
    report = business_metrics(store)

    assert report['followers_per_1000_views'] == pytest.approx(700 / 120_000 * 1000, abs=0.0001)
    assert report['followers_per_1000_views_by_clip'] == {'clip': 2.0, 'clip-b': 25.0}
    assert report['profile_visits'] == 2100
    assert report['follow_conversion_samples'] == 2


def test_follower_conversion_stays_unknown_without_positive_view_denominator(tmp_path):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from analytics.reports import business_metrics
    store, _, _ = prepared(tmp_path)
    collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', views=0,
        profile_visits=0, followers_generated=0))
    report = business_metrics(store)

    assert report['followers_per_1000_views'] is None
    assert report['followers_per_1000_views_by_clip'] == {}
    assert report['profile_visits'] == 0
    assert report['follow_conversion_samples'] == 0


def test_growth_insights_reports_only_measured_patterns_with_minimum_samples(tmp_path):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from analytics.reports import growth_insights
    store, _, path = prepared(tmp_path)
    for index, (duration, followers) in enumerate(((20, 4), (21, 3), (22, 5)), start=1):
        clip_id = f'insight-{index}'
        clip = store.get_clip('clip') | {'id': clip_id, 'path': str(path),
            'sha256': hashlib.sha256(clip_id.encode()).hexdigest(),
            'settings': {'delivery_niche': 'business', 'source_clip_plan': {'duration_seconds': duration},
                         'growth': {'hook': {'hook_type': 'clear_promise'}}}}
        store.save_clip(clip)
        collect_performance(store, ClipPerformance(clip_id=clip_id, platform='instagram',
            views=1000, followers_generated=followers, hashtags=['#Pricing', '#Startup'], cta_used='follow',
            measurement_context=MEASUREMENT_CONTEXT))

    report = growth_insights(store, measurement_context=MEASUREMENT_CONTEXT)

    assert report['status'] == 'measured'
    assert report['measured_clip_count'] == 3
    assert report['best_clips'][0]['clip_id'] == 'insight-3'
    assert report['worst_clips'][0]['clip_id'] == 'insight-2'
    assert report['duration_patterns'] == [{'duration_seconds': 20, 'clip_count': 3,
        'followers_per_1000_views': 4.0}]
    assert report['hook_patterns'] == [{'hook_type': 'clear_promise', 'clip_count': 3,
        'followers_per_1000_views': 4.0}]
    assert report['hashtag_patterns'] == [{'platform': 'instagram',
        'hashtags': ['#pricing', '#startup'], 'clip_count': 3,
        'followers_per_1000_views': 4.0}]
    assert report['cta_patterns'] == [{'platform': 'instagram', 'cta': 'follow', 'clip_count': 3,
        'followers_per_1000_views': 4.0}]


def test_growth_insights_marks_small_samples_insufficient(tmp_path):
    from analytics.reports import growth_insights
    store, _, _ = prepared(tmp_path)

    report = growth_insights(store)

    assert report['status'] == 'insufficient_data'
    assert report['best_clips'] == []
    assert report['duration_patterns'] == []
    assert report['hashtag_patterns'] == []


def test_observed_hashtag_history_uses_smoothed_platform_performance(tmp_path):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from analytics.reports import observed_hashtag_history
    store, _, path = prepared(tmp_path)
    for index, followers in enumerate((10, 8, 12), start=1):
        clip_id = f'tag-winner-{index}'
        store.save_clip(store.get_clip('clip') | {'id': clip_id, 'path': str(path),
            'sha256': hashlib.sha256(clip_id.encode()).hexdigest(),
            'settings': {'delivery_niche': 'business'}})
        collect_performance(store, ClipPerformance(clip_id=clip_id, platform='instagram',
            views=1000, followers_generated=followers, hashtags=['#growth'], measurement_context=MEASUREMENT_CONTEXT))
    for index, followers in enumerate((0, 1, 0), start=1):
        clip_id = f'tag-other-{index}'
        store.save_clip(store.get_clip('clip') | {'id': clip_id, 'path': str(path),
            'sha256': hashlib.sha256(clip_id.encode()).hexdigest(),
            'settings': {'delivery_niche': 'business'}})
        collect_performance(store, ClipPerformance(clip_id=clip_id, platform='instagram',
            views=1000, followers_generated=followers, hashtags=['#stale'], measurement_context=MEASUREMENT_CONTEXT))

    result = observed_hashtag_history(store, 'instagram', measurement_context=MEASUREMENT_CONTEXT)

    assert result['status'] == 'measured'
    assert result['tags']['#growth']['clip_count'] == 3
    assert result['scores']['growth'] > result['scores']['stale']
    assert result['recent_posts'][0] == '#stale'


def test_observed_hashtag_history_ignores_small_samples_and_other_platforms(tmp_path):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from analytics.reports import observed_hashtag_history
    store, _, _ = prepared(tmp_path)
    collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', views=100,
        followers_generated=10, hashtags=['#small']))

    result = observed_hashtag_history(store, 'instagram')

    assert result['status'] == 'insufficient_data'
    assert result['scores'] == {}
    assert result['tags'] == {}


def test_business_metrics_include_utc_day_week_month_aggregates(tmp_path):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from analytics.reports import business_metrics
    store, _, path = prepared(tmp_path)
    store.save_clip(store.get_clip('clip') | {'id': 'clip-two', 'path': str(path)})
    collect_performance(store, ClipPerformance(clip_id='clip', platform='instagram',
        collected_at='2026-10-20T23:30:00Z', views=100, followers_generated=2,
        profile_visits=4, completion_rate=.7, average_watch_time=12))
    collect_performance(store, ClipPerformance(clip_id='clip-two', platform='youtube',
        collected_at='2026-10-21T00:10:00Z', views=200, followers_generated=6,
        profile_visits=8, completion_rate=.9, average_watch_time=20))

    periods = business_metrics(store)['performance_periods']

    assert periods['daily'] == [
        {'period_start': '2026-10-20', 'observations': 1, 'measured_clips': 1,
         'views_samples': 1, 'views': 100, 'followers_samples': 1, 'followers_generated': 2,
         'follower_conversion_samples': 1, 'followers_per_1000_views': 20.0,
         'profile_visits_samples': 1, 'profile_visits': 4, 'completion_rate_samples': 1,
         'completion_rate_mean': .7, 'average_watch_time_samples': 1, 'average_watch_time_mean': 12.0},
        {'period_start': '2026-10-21', 'observations': 1, 'measured_clips': 1,
         'views_samples': 1, 'views': 200, 'followers_samples': 1, 'followers_generated': 6,
         'follower_conversion_samples': 1, 'followers_per_1000_views': 30.0,
         'profile_visits_samples': 1, 'profile_visits': 8, 'completion_rate_samples': 1,
         'completion_rate_mean': .9, 'average_watch_time_samples': 1, 'average_watch_time_mean': 20.0},
    ]
    assert periods['weekly'][0]['period_start'] == '2026-10-19'
    assert periods['weekly'][0]['measured_clips'] == 2
    assert periods['weekly'][0]['followers_per_1000_views'] == 26.6667
    assert periods['monthly'][0]['period_start'] == '2026-10-01'
    assert periods['monthly'][0]['views'] == 300


def test_feedback_needs_independent_clips_and_counts_latest_snapshot_only(tmp_path):
    from analytics.models import ClipPerformance
    from analytics.collectors import collect_performance
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    initial = store.get_clip('clip')
    store.save_clip({**initial, 'settings': {**initial['settings'], 'delivery_niche': 'business'}})
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    for i in range(8):
        collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', views=500,
            completion_rate=.9, collected_at=(now + timedelta(seconds=i)).isoformat(),
            measurement_context=MEASUREMENT_CONTEXT))
    assert feedback_adjustment(store, caption_style='studio', measurement_context=MEASUREMENT_CONTEXT)['adjustment'] == 0
    for index in range(1, 6):
        first = store.get_clip('clip')
        store.save_clip({**first, 'id': 'clip-' + str(index), 'path': str(path),
                         'sha256': hashlib.sha256(str(index).encode()).hexdigest()})
        collect_performance(store, ClipPerformance(clip_id='clip-' + str(index), platform='youtube',
            views=1000, completion_rate=.9, measurement_context=MEASUREMENT_CONTEXT))
    report = feedback_adjustment(store, caption_style='studio', measurement_context=MEASUREMENT_CONTEXT)
    assert report['samples'] == 6
    assert report['adjustment'] == 0
    assert report['supported'] is False  # Repeated success is not an independent comparison.
    assert report['basis']


def feedback_samples(store, path, name, *, count=5, niche='business', platform='youtube',
                     duration=35, question=True, views=1000, completion=.8, followers=None,
                     collected_at=None, measurement_context=MEASUREMENT_CONTEXT):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    initial = store.get_clip('clip')
    for index in range(count):
        identifier = f'{name}-{index}'
        content = f'{name}:{index}'
        store.save_clip({**initial, 'id': identifier, 'path': str(path),
            'sha256': hashlib.sha256(content.encode()).hexdigest(), 'settings': {
            'delivery_niche': niche, 'source': {'id': name},
            'source_clip_plan': {'start_seconds': index * 60, 'duration_seconds': duration},
            'transcript_features': {'opening_question': question}}})
        observation = dict(clip_id=identifier, platform=platform, views=views,
                           completion_rate=completion, followers_generated=followers,
                           measurement_context=measurement_context)
        if collected_at is not None:
            observation['collected_at'] = collected_at
        collect_performance(store, ClipPerformance(**observation))


@pytest.mark.parametrize('identity', ['window', 'hash', 'shifted_window'])
def test_feedback_export_copies_do_not_establish_independent_support(tmp_path, identity):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target')
    feedback_samples(store, path, 'comparison', duration=45, question=False, completion=.2)
    for name in ('target', 'comparison'):
        first = store.get_clip(f'{name}-0')
        for index in range(1, 5):
            clip = store.get_clip(f'{name}-{index}')
            if identity in ('window', 'shifted_window'):
                clip['settings']['source'] = first['settings']['source']
                clip['settings']['source_clip_plan'] = {**first['settings']['source_clip_plan'],
                    'start_seconds': index if identity == 'shifted_window' else 0}
            else:
                clip['sha256'] = first['sha256']
            store.save_clip(clip)
    result = feedback_adjustment(store, caption_style='studio', duration_seconds=35,
                                 opening_question=True, niche='business', platform='youtube', measurement_context=MEASUREMENT_CONTEXT)
    assert result['samples'] == result['comparison_samples'] == 1
    assert result['supported'] is False and result['adjustment'] == 0


def test_future_observations_cannot_establish_feedback_support(tmp_path):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    feedback_samples(store, path, 'target', collected_at=future)
    feedback_samples(store, path, 'comparison', duration=45, question=False, collected_at=future)
    result = feedback_adjustment(store, caption_style='studio', duration_seconds=35,
                                 opening_question=True, niche='business', platform='youtube', measurement_context=MEASUREMENT_CONTEXT)
    assert result['samples'] == result['comparison_samples'] == 0
    assert result['supported'] is False and result['adjustment'] == 0


@pytest.mark.parametrize('views', [None, 0])
def test_feedback_ignores_completion_without_a_positive_view_denominator(tmp_path, views):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'unexposed', views=views)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35, opening_question=True, measurement_context=MEASUREMENT_CONTEXT)
    assert report['samples'] == 0
    assert report['adjustment'] == 0 and report['supported'] is False


def test_feedback_prefers_measured_followers_to_a_conflicting_completion_pattern(tmp_path):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'follow-winner', completion=.2, followers=20)
    feedback_samples(store, path, 'completion-winner', duration=45, question=False, completion=.9, followers=1)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35, opening_question=True, measurement_context=MEASUREMENT_CONTEXT)
    assert report['adjustment'] > 0
    assert report['metric'] == 'followers_per_view'
    assert report['samples'] == report['comparison_samples'] == 5
    assert report['smoothed_outcome'] < report['average_outcome']


def test_feedback_requires_an_independent_comparison_group(tmp_path):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target')
    feedback_samples(store, path, 'comparator', count=4, duration=45, question=False, completion=.4)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35, opening_question=True, measurement_context=MEASUREMENT_CONTEXT)
    assert report['supported'] is False
    assert report['adjustment'] == 0


@pytest.mark.parametrize('other', [{'niche': 'sports'}, {'platform': 'tiktok'}])
def test_feedback_does_not_infer_one_cohort_from_mixed_niches_or_platforms(tmp_path, other):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'business-youtube')
    feedback_samples(store, path, 'other-cohort', **other)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35, opening_question=True, measurement_context=MEASUREMENT_CONTEXT)
    assert report['supported'] is False
    assert report['adjustment'] == 0


def test_explicit_feedback_cohort_excludes_other_niches_and_platforms(tmp_path):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', completion=.8)
    feedback_samples(store, path, 'comparison', duration=45, question=False, completion=.4)
    for name, other in [('sports', {'niche': 'sports'}), ('tiktok', {'platform': 'tiktok'})]:
        feedback_samples(store, path, name + '-target', completion=.1, followers=0, **other)
        feedback_samples(store, path, name + '-comparison', duration=45, question=False,
                         completion=.9, followers=100, **other)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35,
                                 opening_question=True, niche='Business', platform='youtube', measurement_context=MEASUREMENT_CONTEXT)
    assert report['supported'] is True
    assert report['samples'] == report['comparison_samples'] == 5
    assert report['cohort']['niche'] == 'business' and report['cohort']['platform'] == 'youtube'
    assert report['metric'] == 'completion_rate'
    assert report['adjustment'] == pytest.approx(.016667, abs=.000001)


def test_equal_cohort_outcomes_do_not_get_a_boost_from_an_arbitrary_completion_target(tmp_path):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', completion=.9)
    feedback_samples(store, path, 'comparison', duration=45, question=False, completion=.9)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35, opening_question=True, measurement_context=MEASUREMENT_CONTEXT)
    assert report['supported'] is True
    assert report['adjustment'] == 0
    assert report['comparison_outcome'] == pytest.approx(.9)


def test_unclassified_feedback_history_cannot_be_used_as_a_niche_cohort(tmp_path):
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', niche='unclassified')
    feedback_samples(store, path, 'comparison', niche='unclassified', duration=45, question=False)
    report = feedback_adjustment(store, caption_style='studio', duration_seconds=35, opening_question=True, measurement_context=MEASUREMENT_CONTEXT)
    assert report['supported'] is False
    assert report['adjustment'] == 0
    assert report.get('reason') == 'ambiguous_niche'


def test_order_feedback_uses_campaign_platform_and_selected_source_niche(tmp_path):
    from types import SimpleNamespace
    from analytics.feedback import feedback_for_order
    store, campaign, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', completion=.8)
    feedback_samples(store, path, 'comparison', duration=45, question=False, completion=.4)
    feedback_samples(store, path, 'other-platform', platform='tiktok', completion=.1)
    controller = SimpleNamespace(store=store, state={'source_selection': {'niches': ['Business']}},
        config=SimpleNamespace(caption_style='studio', campaign_id=campaign.id, niche=None, measurement_context=MEASUREMENT_CONTEXT))
    evaluate = feedback_for_order(controller)
    moment = {'clip_plan': {'duration_seconds': 35}, 'transcript_features': {'opening_question': True}}
    report = evaluate(moment)
    assert report['supported'] is True
    assert report['cohort']['platform'] == 'youtube'
    controller.state['source_selection'] = {'niches': ['Sports']}
    assert evaluate(moment)['supported'] is False


def test_order_feedback_excludes_outcomes_collected_after_order_started(tmp_path):
    from types import SimpleNamespace
    from analytics.feedback import feedback_for_order
    store, campaign, path = prepared(tmp_path)
    feedback_samples(store, path, 'target', completion=.8)
    feedback_samples(store, path, 'comparison', duration=45, question=False, completion=.4)
    controller = SimpleNamespace(store=store, state={
        'created_at': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        'source_selection': {'niches': ['Business']}}, config=SimpleNamespace(
            caption_style='studio', campaign_id=campaign.id, niche=None, measurement_context=MEASUREMENT_CONTEXT))
    report = feedback_for_order(controller)({'clip_plan': {'duration_seconds': 35},
        'transcript_features': {'opening_question': True}})
    assert report['supported'] is False and report['adjustment'] == 0
    assert report['samples'] == report['comparison_samples'] == 0


def test_business_metrics_report_unknown_reward_and_publish_rates(tmp_path):
    from analytics.reports import business_metrics
    store, _, _ = prepared(tmp_path)
    report = business_metrics(store)
    assert report['clips_generated'] == 1
    assert report['publish_success_rate'] is None
    assert report['reward_per_clip'] is None


def test_business_metrics_include_measured_cache_efficiency(tmp_path):
    from analytics.reports import business_metrics
    from app.repositories.cache import CacheRepository
    store, _, _ = prepared(tmp_path)
    cache = CacheRepository(store)
    cache.record_access('downloaded_section', 'exact_hit', reused_bytes=4096, requested_seconds=30)
    cache.record_access('downloaded_section', 'miss', requested_seconds=20)

    report = business_metrics(store)

    assert report['cache_requests'] == 2
    assert report['cache_hits'] == 1 and report['cache_misses'] == 1
    assert report['cache_hit_rate'] == .5
    assert report['cache_bytes_reused'] == 4096


def test_reward_per_clip_sums_platform_rewards_before_averaging_clips(tmp_path):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from analytics.reports import business_metrics
    store, _, path = prepared(tmp_path)
    store.save_clip({**store.get_clip('clip'), 'id': 'clip-2', 'path': str(path)})
    collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', reward_amount='1.00'))
    collect_performance(store, ClipPerformance(clip_id='clip', platform='tiktok', reward_amount='3.00'))
    collect_performance(store, ClipPerformance(clip_id='clip-2', platform='youtube', reward_amount='2.00'))
    report = business_metrics(store)
    assert report['reward_per_clip'] == '3.00'


def test_invalid_reward_amount_is_a_value_error(tmp_path):
    from analytics.models import ClipPerformance
    with pytest.raises(ValueError):
        ClipPerformance(clip_id='clip', platform='youtube', reward_amount='not-money')


def test_clips_per_day_uses_calendar_span_and_pipeline_duration_uses_order_runs(tmp_path):
    from analytics.reports import business_metrics
    from app.repositories.database import timestamp
    from datetime import timedelta
    store, _, path = prepared(tmp_path)
    first = store.get_clip('clip')
    first_day = datetime.fromisoformat(first['created_at'])
    store.save_clip({**first, 'id': 'clip-2', 'path': str(path),
                     'created_at': (first_day + timedelta(days=2)).isoformat()})
    with store.connection(write=True) as db:
        db.execute('INSERT INTO pipeline_events VALUES (?,?,?,?,?,?,?)',
            ('duration-a', first['order_id'], None, 'finished', 'order_updated', timestamp(),
             '{"duration_ms":1000}'))
        db.execute('INSERT INTO pipeline_events VALUES (?,?,?,?,?,?,?)',
            ('duration-b', first['order_id'], None, 'finished', 'order_updated', timestamp(),
             '{"duration_ms":2000}'))
    report = business_metrics(store)
    assert report['clips_generated_per_day'] == pytest.approx(2 / 3)
    assert report['average_pipeline_duration_ms'] == 3000
    assert report['successful_render_rate'] is None


def test_render_success_rate_counts_measured_attempts_only(tmp_path):
    from analytics.reports import business_metrics
    store, _, _ = prepared(tmp_path)
    store.record_render_event('order-1', 'clip-1', 'started', 'attempt-1')
    store.record_render_event('order-1', 'clip-1', 'succeeded', 'attempt-1')
    store.record_render_event('order-1', 'clip-2', 'started', 'attempt-2')
    store.record_render_event('order-1', 'clip-2', 'failed', 'attempt-2')
    report = business_metrics(store)
    assert report['render_attempts'] == 2
    assert report['successful_render_rate'] == .5


def test_reward_per_hour_joins_rewards_to_their_order_durations(tmp_path):
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from analytics.reports import business_metrics
    from app.repositories.database import timestamp
    store, _, _ = prepared(tmp_path)
    clip = store.get_clip('clip')
    collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', reward_amount='3.00'))
    with store.connection(write=True) as db:
        for key, order_id, duration in [('rewarded', clip['order_id'], 1800000),
                                        ('unmatched', 'unrelated-order', 9000000)]:
            db.execute('INSERT INTO pipeline_events VALUES (?,?,?,?,?,?,?)',
                (key, order_id, None, 'finished', 'order_updated', timestamp(),
                 '{"duration_ms":' + str(duration) + '}'))
    assert business_metrics(store)['reward_per_hour'] == 6


def test_negative_or_unknown_campaign_flags_are_not_measured_decisions(tmp_path):
    from analytics.models import ClipPerformance
    from analytics.collectors import collect_performance
    from analytics.reports import business_metrics
    store, _, _ = prepared(tmp_path)
    collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', campaign_rejected=False))
    report = business_metrics(store)
    assert report['campaign_acceptance_rate'] is None
    assert report['campaign_decisions'] == 0


def test_failed_local_preparation_is_not_a_network_publication_attempt(tmp_path, monkeypatch):
    from publishing.manager import PublishingManager
    from analytics.reports import business_metrics
    store, campaign, _ = prepared(tmp_path)
    manager = PublishingManager(store, output=tmp_path / 'manual')
    monkeypatch.setattr(manager.publisher, 'publish', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(Exception):
        manager.publish('clip', {'caption': '#example'}, campaign_id=campaign.id, platform='youtube', key='failed')
    report = business_metrics(store)
    assert report['publish_success_rate'] is None
    assert report['publication_attempts'] == 0
