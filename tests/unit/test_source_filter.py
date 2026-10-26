from datetime import datetime, timedelta, timezone


def source_filter_config():
    from app.core.config import load_settings
    return load_settings(environ={}).source_filter


def test_source_filter_scores_available_metadata_and_reports_unknowns():
    from growth.source import SourcePreFilter

    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    source = {'title': 'Startup founder explains pricing', 'views': 200_000,
              'views_per_hour_since_upload': 1500,
              'published_at': (now - timedelta(days=2)).isoformat(), 'duration': 3600}
    report = SourcePreFilter(source_filter_config()).score(source, keywords=['startup', 'pricing'], now=now)

    assert 0 <= report['score'] <= 1
    assert report['signals']['velocity']['value'] is not None
    assert report['signals']['freshness']['value'] is not None
    assert report['signals']['relevance']['value'] > 0
    assert report['signals']['replay_available']['value'] is None
    assert report['evidence_coverage'] < 1
    assert report['missing_signals']


def test_source_filter_does_not_reject_when_available_evidence_is_too_sparse():
    from growth.source import SourcePreFilter

    prefilter = SourcePreFilter(source_filter_config())
    weak = prefilter.score({'title': 'Unknown video'}, keywords=[])

    assert weak['evidence_coverage'] < prefilter.config.minimum_coverage
    decision = prefilter.accepts(weak)
    assert decision['accepted'] is True
    assert decision['basis'] == 'insufficient_evidence'


def test_source_filter_rejects_low_score_only_after_minimum_evidence():
    from growth.source import SourcePreFilter

    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    source = {'title': 'Unrelated clip', 'views': 10, 'views_per_hour_since_upload': 0.01,
              'published_at': (now - timedelta(days=13)).isoformat(), 'duration': 3600,
              'likes': 0, 'comments': 0}
    prefilter = SourcePreFilter(source_filter_config())
    report = prefilter.score(source, keywords=['business', 'founder'], now=now)

    assert report['evidence_coverage'] >= prefilter.config.minimum_coverage
    decision = prefilter.accepts(report)
    assert decision['accepted'] is False
    assert decision['basis'] == 'metadata_score_below_threshold'


def test_source_filter_uses_configured_weights_and_keeps_all_unknown_unscored():
    from growth.source import SourcePreFilter

    report = SourcePreFilter(source_filter_config()).score({})
    assert report['score'] is None
    assert report['evidence_coverage'] == 0
    assert len(report['missing_signals']) == len(report['weights'])


def test_source_filter_ranks_metadata_candidates_and_keeps_rejection_evidence():
    from growth.source import SourcePreFilter

    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    prefilter = SourcePreFilter(source_filter_config())
    candidates = [
        {'id': 'weak', 'title': 'Unrelated clip', 'views': 10,
         'views_per_hour_since_upload': 0.01,
         'published_at': (now - timedelta(days=13)).isoformat(), 'duration': 3600,
         'likes': 0, 'comments': 0},
        {'id': 'strong', 'title': 'Business founder pricing strategy', 'views': 500_000,
         'views_per_hour_since_upload': 2000,
         'published_at': (now - timedelta(days=1)).isoformat(), 'duration': 3600,
         'likes': 10_000, 'comments': 5000},
    ]

    ranked = prefilter.rank(candidates, keywords=['business', 'founder'], now=now)

    assert [item['id'] for item in ranked] == ['strong']
    assert ranked[0]['source_prefilter']['decision']['accepted'] is True
