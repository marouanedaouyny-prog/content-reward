"""Learned reports keep account, measurement and independent content scopes."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from analytics.collectors import collect_performance
from analytics.models import ClipPerformance
from analytics.reports import growth_insights, observed_hashtag_history
from test_publishing import prepared

CONTEXT = {'account_id': 'owned-channel', 'reporting_window_hours': 24.0,
           'view_definition': 'engaged_views', 'definition_version': 'v1'}
COLLECTED = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
CUTOFF = COLLECTED + timedelta(hours=2)


def sample(store, name, *, index=0, platform='instagram', niche='business', context=CONTEXT,
           followers=10, views=1000, tags=('#growth',), cta='follow', collected=COLLECTED,
           digest=None, source=None, start=None, duration=35):
    original = store.get_clip('clip')
    store.save_clip({**original, 'id': name,
        'sha256': digest if digest is not None else hashlib.sha256(name.encode()).hexdigest(),
        'settings': {'delivery_niche': niche, 'source': {'id': source or name},
            'source_clip_plan': {'start_seconds': index * 100 if start is None else start,
                                 'duration_seconds': duration},
            'growth': {'hook': {'hook_type': 'clear_promise'}}}})
    collect_performance(store, ClipPerformance(clip_id=name, platform=platform, views=views,
        followers_generated=followers, hashtags=list(tags) if tags is not None else None,
        cta_used=cta, collected_at=collected.isoformat(), measurement_context=context))


def three_samples(store, prefix='sample', **kwargs):
    for index in range(3):
        sample(store, f'{prefix}-{index}', index=index, **kwargs)


@pytest.mark.parametrize('context', [None, {}, {'account_id': 'owned-channel'},
    {**CONTEXT, 'view_definition': 'unknown'}])
def test_reports_without_complete_context_never_emit_learned_recommendations(tmp_path, context):
    store, _, _ = prepared(tmp_path)
    three_samples(store)
    options = {'measurement_context': context} if context is not None else {}
    history = observed_hashtag_history(store, 'instagram', **options)
    insights = growth_insights(store, **options)
    assert history['status'] == insights['status'] == 'insufficient_data'
    assert history['reason'] == insights['reason'] == 'learning_context_required'
    assert history['scores'] == {} and history['recent_posts'] == []
    for key in ('best_clips', 'worst_clips', 'duration_patterns', 'hook_patterns',
                'hashtag_patterns', 'cta_patterns', 'cohorts'):
        assert insights[key] == []


@pytest.mark.parametrize('other_context', [
    {**CONTEXT, 'account_id': 'another-channel'},
    {**CONTEXT, 'reporting_window_hours': 168},
    {**CONTEXT, 'view_definition': 'play_starts'},
    {**CONTEXT, 'definition_version': 'v2'},
    {**CONTEXT, 'definition_version': None},
])
def test_context_filter_precedes_latest_snapshot_for_both_reports(tmp_path, other_context):
    store, _, _ = prepared(tmp_path)
    three_samples(store)
    for index in range(3):
        sample(store, f'sample-{index}', index=index, context=other_context,
               followers=999, tags=('#leaked',), collected=COLLECTED + timedelta(hours=1))
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    history = observed_hashtag_history(store, 'instagram', **options)
    insights = growth_insights(store, **options)
    assert history['status'] == insights['status'] == 'measured'
    assert history['tags']['#growth']['followers_per_1000_views'] == 10
    assert '#leaked' not in history['tags']
    assert history['recent_posts'] == ['#growth'] * 3
    assert insights['measured_clip_count'] == 3
    assert insights['best_clips'][0]['followers_per_1000_views'] == 10
    assert history['measurement_context'] == insights['measurement_context'] == CONTEXT
    assert history['cohort']['niche'] == insights['cohort']['niche'] == 'business'


def test_as_of_applies_to_reports_and_hashtag_freshness(tmp_path):
    store, _, _ = prepared(tmp_path)
    three_samples(store)
    for index in range(3):
        sample(store, f'sample-{index}', index=index, tags=('#future',), followers=999,
               collected=CUTOFF + timedelta(seconds=1))
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF.isoformat()}
    history = observed_hashtag_history(store, 'instagram', **options)
    insights = growth_insights(store, **options)
    assert history['recent_posts'] == ['#growth'] * 3
    assert history['scores'].keys() == {'growth'}
    assert insights['best_clips'][0]['followers'] == 10


@pytest.mark.parametrize('identity', ['window', 'overlapping_windows', 'hash', 'transitive'])
def test_copied_content_cannot_create_report_support(tmp_path, identity):
    store, _, _ = prepared(tmp_path)
    for index in range(3):
        options = {}
        if identity in ('window', 'overlapping_windows'):
            options = {'source': 'same-source',
                       'start': 10 + index if identity == 'overlapping_windows' else 10}
        elif identity == 'hash':
            options = {'digest': hashlib.sha256(b'same-copy').hexdigest()}
        elif index < 2:
            options = {'digest': hashlib.sha256(b'first-pair').hexdigest()}
        if identity == 'transitive' and index > 0:
            options.update(source='second-pair', start=20)
        sample(store, f'copy-{index}', index=index, **options)
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    history = observed_hashtag_history(store, 'instagram', **options)
    insights = growth_insights(store, **options)
    assert history['status'] == insights['status'] == 'insufficient_data'
    assert history['scores'] == {}
    assert history['tags']['#growth']['clip_count'] == 1
    assert insights['measured_clip_count'] == 1 and insights['best_clips'] == []
    assert insights['duration_patterns'] == insights['hashtag_patterns'] == []


def test_unknown_content_identities_do_not_establish_support(tmp_path):
    store, _, _ = prepared(tmp_path)
    three_samples(store)
    for index in range(3):
        clip = store.get_clip(f'sample-{index}')
        clip['sha256'] = 'unknown'
        clip['settings']['source'] = {}
        store.save_clip(clip)
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    assert observed_hashtag_history(store, 'instagram', **options)['scores'] == {}
    assert growth_insights(store, **options)['measured_clip_count'] == 0


@pytest.mark.parametrize('missing', [{'followers': None}, {'views': 0}, {'views': None}])
def test_latest_unknown_copy_does_not_resurrect_an_older_favorable_copy(tmp_path, missing):
    store, _, _ = prepared(tmp_path)
    three_samples(store)
    sample(store, 'new-copy', source='sample-0', start=0, collected=COLLECTED + timedelta(hours=1),
           tags=None, **missing)
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    history = observed_hashtag_history(store, 'instagram', **options)
    insights = growth_insights(store, **options)
    assert history['scores'] == {}
    assert insights['measured_clip_count'] == 2 and insights['best_clips'] == []


def test_report_patterns_and_rankings_never_pool_platforms_or_niches(tmp_path):
    store, _, _ = prepared(tmp_path)
    three_samples(store, 'business')
    three_samples(store, 'sports', niche='sports', followers=90, tags=('#sports',))
    three_samples(store, 'tiktok', platform='tiktok', followers=99, tags=('#elsewhere',))
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    report = growth_insights(store, **options)
    assert report['status'] == 'insufficient_data' and report['reason'] == 'ambiguous_platform'
    assert report['best_clips'] == report['duration_patterns'] == []
    assert len(report['cohorts']) == 3
    assert all(cohort['measured_clip_count'] == 3 for cohort in report['cohorts'])
    chosen = growth_insights(store, platform='instagram', niche='Business', **options)
    assert chosen['status'] == 'measured' and chosen['measured_clip_count'] == 3
    assert chosen['best_clips'][0]['followers_per_1000_views'] == 10
    history = observed_hashtag_history(store, 'instagram', **options)
    assert history['status'] == 'insufficient_data' and history['reason'] == 'ambiguous_niche'
    assert history['scores'] == {} and history['recent_posts'] == []
    selected = observed_hashtag_history(store, 'instagram', niche='business', **options)
    assert selected['scores'].keys() == {'growth'}
    assert selected['recent_posts'] == ['#growth'] * 3


def test_sparse_other_cohort_still_makes_unselected_recommendations_ambiguous(tmp_path):
    store, _, _ = prepared(tmp_path)
    three_samples(store)
    sample(store, 'sparse-sports', niche='sports')
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    assert growth_insights(store, **options)['reason'] == 'ambiguous_niche'
    assert observed_hashtag_history(store, 'instagram', **options)['scores'] == {}


def test_content_representative_is_chosen_before_pattern_and_tag_grouping(tmp_path):
    store, _, _ = prepared(tmp_path)
    three_samples(store)
    for index in range(3):
        sample(store, f'copy-{index}', source=f'sample-{index}', start=index * 100,
               digest=hashlib.sha256(f'sample-{index}'.encode()).hexdigest(),
               collected=COLLECTED + timedelta(hours=1), tags=('#replacement',), cta='save', duration=45)
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    history = observed_hashtag_history(store, 'instagram', **options)
    insights = growth_insights(store, **options)
    assert history['scores'].keys() == {'replacement'}
    assert history['recent_posts'] == ['#replacement'] * 3
    assert insights['measured_clip_count'] == 3
    assert insights['duration_patterns'][0]['duration_seconds'] == 45
    assert len(insights['duration_patterns']) == 1
    assert insights['cta_patterns'][0]['cta'] == 'save'
    assert insights['hashtag_patterns'][0]['hashtags'] == ['#replacement']


@pytest.mark.parametrize(('saved', 'chosen', 'expected'), [
    ('business', 'Business', 'business'), ('AI & technology', 'ai-technology', 'ai-technology'),
])
def test_selected_report_niche_uses_canonical_library_aliases(tmp_path, saved, chosen, expected):
    store, _, _ = prepared(tmp_path)
    three_samples(store, niche=saved)
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF, 'niche': chosen}
    assert growth_insights(store, **options)['cohort']['niche'] == expected
    assert observed_hashtag_history(store, 'instagram', **options)['cohort']['niche'] == expected


def test_unclassified_history_cannot_support_report_recommendations(tmp_path):
    store, _, _ = prepared(tmp_path)
    three_samples(store, niche='unclassified')
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    history = observed_hashtag_history(store, 'instagram', **options)
    insights = growth_insights(store, **options)
    assert history['reason'] == insights['reason'] == 'ambiguous_niche'
    assert history['scores'] == {} and insights['best_clips'] == []
    assert history['cohorts'] == insights['cohorts'] == []


def test_scoped_reports_keep_cold_start_when_all_observations_are_after_cutoff(tmp_path):
    store, _, _ = prepared(tmp_path)
    three_samples(store)
    options = {'measurement_context': CONTEXT, 'as_of': COLLECTED - timedelta(seconds=1)}
    history = observed_hashtag_history(store, 'instagram', **options)
    insights = growth_insights(store, **options)
    assert history['status'] == insights['status'] == 'insufficient_data'
    assert history['scores'] == {} and history['recent_posts'] == []
    assert insights['measured_clip_count'] == 0 and insights['best_clips'] == []


def test_each_pattern_requires_its_own_support_and_conversion_is_view_weighted(tmp_path):
    store, _, _ = prepared(tmp_path)
    sample(store, 'small-denominator', views=10, followers=1)
    sample(store, 'large-denominator', views=10_000, followers=10)
    sample(store, 'other-pattern', views=990, followers=0, tags=('#different',), duration=45)
    options = {'measurement_context': CONTEXT, 'as_of': CUTOFF}
    report = growth_insights(store, **options)
    assert report['status'] == 'measured'
    assert report['duration_patterns'] == report['hashtag_patterns'] == []
    assert report['hook_patterns'][0]['followers_per_1000_views'] == 1
    history = observed_hashtag_history(store, 'instagram', **options)
    assert history['scores'] == {}
    assert history['baseline_followers_per_1000_views'] == 1


@pytest.mark.parametrize('minimum', [0, -1, True, 1.5])
def test_report_support_minimum_must_be_a_positive_integer(tmp_path, minimum):
    store, _, _ = prepared(tmp_path)
    with pytest.raises(ValueError, match='minimum'):
        growth_insights(store, minimum, measurement_context=CONTEXT)
    with pytest.raises(ValueError, match='minimum'):
        observed_hashtag_history(store, 'instagram', minimum, measurement_context=CONTEXT)


@pytest.mark.parametrize('prior', [-1, float('inf'), float('nan'), True])
def test_hashtag_prior_must_be_finite_and_nonnegative(tmp_path, prior):
    store, _, _ = prepared(tmp_path)
    with pytest.raises(ValueError, match='prior'):
        observed_hashtag_history(store, 'instagram', prior_views=prior, measurement_context=CONTEXT)
