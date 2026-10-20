import importlib
import json

import pytest


def row(index=1, **changes):
    return {'content_id': str(7500000000000000000 + index), 'create_time': '2025-08-01T12:00:00Z',
            'desc': 'AI software tutorial #software', 'duration': 25, 'views': 100,
            'likes': 5, 'comments': 1, 'shares': 2, 'saves': 3,
            'language': 'en', 'country': 'US', 'is_video': 1, 'is_ad': 0} | changes


def analyze(rows, **options):
    module = importlib.import_module('clipping.research')
    content = '\n'.join(json.dumps(item) for item in rows).encode()
    return module.analyze_metadata(content, 'sample.jsonl', **options)


def test_large_ids_duplicates_and_invalid_rows_are_counted_without_exposing_captions():
    report = analyze([row(), row(), row(2, views=-1), row(3, duration='NaN')], keywords='AI')
    assert report['valid_records'] == 1
    assert report['duplicate_records'] == 1
    assert report['invalid_records'] == 2
    assert report['source'] == 'operator_sample'
    assert report['cohorts'] == []
    assert 'AI software tutorial' not in json.dumps(report)
    assert 'probability' not in report


def test_cohorts_keep_month_and_language_separate_and_handle_zero_views():
    rows = [row(i, views=0) for i in range(1, 11)]
    rows += [row(i, create_time='2025-09-01T12:00:00Z', views=200) for i in range(11, 21)]
    rows += [row(i, language='ar', views=300) for i in range(21, 31)]
    report = analyze(rows, keywords='AI')
    assert len(report['cohorts']) == 3
    empty_views = next(item for item in report['cohorts'] if item['median_views'] == 0)
    assert empty_views['median_share_rate'] is None
    assert empty_views['median_save_rate'] is None
    assert report['matched_records'] == 30
    assert {item['month'] for item in report['cohorts']} == {'2025-08', '2025-09'}


def test_topic_matching_has_word_boundaries_and_filters():
    rows = [row(i, desc='air travel', country='FR') for i in range(1, 11)]
    rows += [row(i, desc='AI tutorial', country='US') for i in range(11, 21)]
    report = analyze(rows, keywords='AI', country='US', language='en')
    assert report['matched_records'] == 10
    assert report['cohorts'][0]['count'] == 10


def test_csv_and_synthetic_demo_are_usable():
    module = importlib.import_module('clipping.research')
    content = b'content_id,create_time,desc,duration,views\n7500000000000000001,2025-08-01T00:00:00Z,AI,20,5\n'
    assert module.analyze_metadata(content, 'sample.csv')['valid_records'] == 1
    report = module.demo_report()
    assert report['source'] == 'synthetic_demo'
    assert report['cohorts']
    assert all(item['count'] >= 10 for item in report['cohorts'])


def test_import_limits_and_missing_schema_fail_with_actionable_errors():
    module = importlib.import_module('clipping.research')
    with pytest.raises(ValueError, match='CSV or JSONL'):
        module.analyze_metadata(b'anything', 'sample.parquet')
    with pytest.raises(ValueError, match='records'):
        analyze([])
    with pytest.raises(ValueError, match='valid'):
        analyze([{'desc': 'no metrics'}])
    with pytest.raises(ValueError, match='25 MB'):
        module.analyze_metadata(b'x' * (module.MAX_BYTES + 1), 'sample.csv')


def test_missing_views_and_invalid_flags_are_not_silently_treated_as_zero():
    missing = row()
    del missing['views']
    report = analyze([missing, row(2, is_video=2), row(3)])
    assert report['valid_records'] == 1
    assert report['invalid_records'] == 2


def test_malformed_csv_fields_return_a_validation_error():
    module = importlib.import_module('clipping.research')
    with pytest.raises(ValueError, match='CSV'):
        module.analyze_metadata(b'desc\n' + b'x' * 150000, 'sample.csv')


def test_brief_compares_engagement_only_inside_the_best_supported_context():
    rows = [row(i, duration=25, shares=2) for i in range(1, 21)]
    rows += [row(i, desc='gaming tutorial', duration=40, shares=8) for i in range(21, 31)]
    # A different language/month has better counts but cannot win this comparison.
    rows += [row(i, language='fr', create_time='2025-09-01T00:00:00Z', shares=90)
             for i in range(31, 41)]
    report = analyze(rows, keywords='AI,gaming')
    brief = report['planning_brief']
    assert (brief['topic'], brief['language'], brief['month']) == ('gaming', 'en', '2025-08')
    assert brief['keywords'] == ['gaming']
    assert brief['target_duration'] == 40
    assert brief['basis'] == 'share_rate'
    assert brief['compared_cohorts'] == 2
    assert brief['support_count'] == 10
    assert brief['can_apply'] is True
    assert 'historical' in brief['note'].lower()


def test_missing_rates_remain_unknown_and_brief_falls_back_to_sample_support():
    rows = [row(i, duration=25) for i in range(1, 21)]
    for item in rows:
        item.pop('shares')
        item['saves'] = ''
    rows += [row(i, duration=40, shares=80) for i in range(21, 31)]
    # Fewer than ten measured rates cannot support a comparative recommendation.
    rows[-1]['views'] = 0
    report = analyze(rows, keywords='AI')
    cohort = next(item for item in report['cohorts'] if item['count'] == 20)
    assert cohort['median_share_rate'] is None and cohort['median_save_rate'] is None
    assert cohort['share_observations'] == 0
    assert report['planning_brief']['basis'] == 'sample_support'
    assert report['planning_brief']['target_duration'] == 25


def test_demo_sparse_unknown_and_unrenderable_samples_cannot_supply_live_recommendations():
    module = importlib.import_module('clipping.research')
    assert module.demo_report()['planning_brief']['can_apply'] is False
    for rows in ([row()], [row(i, language='') for i in range(1, 11)],
                 [row(i, country='') for i in range(1, 11)],
                 [row(i, duration=240) for i in range(1, 11)]):
        report = analyze(rows, keywords='AI')
        assert report['planning_brief'] is None
        assert report['brief_note']
