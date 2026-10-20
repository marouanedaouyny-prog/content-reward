"""Selection uses observable evidence; unknown signals never become invented scores."""

import pytest


def test_weighted_score_reports_unknown_signals_and_measured_contributions():
    from clipping.selection.scoring import score_signals
    report = score_signals({'hook': .8, 'completeness': 1},
                           {'hook': .5, 'completeness': .25, 'replay': .25})
    assert report['score'] == pytest.approx(.65 / .75)
    assert report['evidence_coverage'] == .75
    assert report['missing_signals'] == ['replay']
    assert report['signals']['replay']['value'] is None
    assert report['signals']['hook']['weighted_contribution'] == pytest.approx(.4)


@pytest.mark.parametrize('value', [True, float('nan'), -0.1, 1.1])
def test_scores_reject_invalid_supplied_signals(value):
    from clipping.selection.scoring import score_signals
    with pytest.raises(ValueError):
        score_signals({'hook': value}, {'hook': 1.0})


def test_configuration_controls_actual_candidate_ranking():
    from app.core.config import load_settings
    from clipping.planning import suggest_cuts
    transcript = [
        {'start': 0, 'end': 30, 'text': 'Why does a business need three cash reserves? Build a financial plan.'},
        {'start': 100, 'end': 130, 'text': 'Practice improves judgment. Review decisions after every project.'},
    ]
    replay = [{'start_time': 0, 'end_time': 50, 'value': .1},
              {'start_time': 50, 'end_time': 180, 'value': 1.0}]
    settings = load_settings(environ={})
    settings.selection.weights = dict.fromkeys(settings.selection.weights, 0.0)
    settings.selection.weights['replay'] = 1.0
    replay_choice = suggest_cuts(transcript, 180, 30, 30, 30, 'business', replay,
                                settings=settings)[0]
    settings.selection.weights['replay'] = 0.0
    settings.selection.weights['semantic'] = 1.0
    text_choice = suggest_cuts(transcript, 180, 30, 30, 30, 'business', replay,
                              settings=settings)[0]
    assert replay_choice['clip_plan']['start_seconds'] == 100
    assert text_choice['clip_plan']['start_seconds'] == 0
    assert 'emotion' in text_choice['selection']['missing_signals']
    assert text_choice['selection']['signals']['semantic']['basis']


def test_candidate_anchors_merge_strategies_without_duplicating_source_windows():
    from clipping.planning import suggest_cuts
    transcript = [
        {'start': 0, 'end': 10, 'text': 'A complete introduction.'},
        {'start': 10, 'end': 20, 'text': 'Why does budgeting matter?'},
        {'start': 20, 'end': 40, 'text': 'Budgeting protects cash reserves. Make a plan before spending.'},
    ]
    choices = suggest_cuts(transcript, 100, 30, 30, 30, 'budgeting',
                          chapters=[{'start_time': 10, 'end_time': 40, 'title': 'Budgets'}])
    moment = next(item for item in choices if item['clip_plan']['start_seconds'] == 10)
    assert {'question_answer', 'keyword', 'chapter', 'transcript_boundary'} <= set(moment['strategies'])
    assert len({tuple(item['clip_plan'].values()) for item in choices}) == len(choices)


def test_source_metrics_preserve_unknown_age_and_actual_engagement():
    from clipping.selection.scoring import source_signals
    report = source_signals({'view_count': 1000, 'like_count': 90, 'comment_count': 10})
    assert report['views_per_hour'] is None
    assert report['engagement_rate'] == .1
    assert source_signals({'view_count': 0})['engagement_rate'] is None


def test_replay_measurement_excludes_cues_outside_the_selected_window():
    from clipping.planning import suggest_cuts
    transcript = [
        {'start': 0, 'end': 20, 'text': 'Practice develops judgment. Review completed work.'},
        {'start': 20, 'end': 40, 'text': 'Budgeting protects cash reserves. Spend deliberately.'},
        {'start': 40, 'end': 60, 'text': 'Hiring benefits from clear roles. Write the role first.'},
    ]
    choices = suggest_cuts(transcript, 60, 20, 20, 20, heatmap=[
        {'start_time': 0, 'end_time': 20, 'value': .1},
        {'start_time': 20, 'end_time': 60, 'value': 1.0}])
    first = next(item for item in choices if item['clip_plan']['start_seconds'] == 0)
    assert first['replay_peak'] == .1
    assert first['replay_score'] == pytest.approx(.1)


@pytest.mark.parametrize('embedding', [[0.0, 0.0], [float('nan'), 1.0], [True, 0.0], [1.0]])
def test_invalid_embeddings_do_not_fabricate_semantic_evidence(embedding):
    from clipping.selection.dedup import compare_moments
    report = compare_moments({'source_excerpt': 'One thought.', 'embedding': embedding, 'embedding_model': 'model'},
                             {'source_excerpt': 'Other thought.', 'embedding': [1.0, 0.0], 'embedding_model': 'model'})
    assert report['semantic_similarity'] is None and not report['duplicate']


def test_quote_detection_normalizes_unicode_apostrophes():
    from clipping.selection.dedup import compare_moments
    report = compare_moments(
        {'source_excerpt': "Don't hire before you've built cash reserves for payroll and taxes."},
        {'source_excerpt': 'Don’t hire before you’ve built cash reserves for payroll and taxes.'})
    assert report['duplicate'] and report['repeated_quote']


def test_duplicates_include_contained_intervals_and_repeated_quotes_across_sources():
    from clipping.selection.dedup import compare_moments
    earlier = {'source_id': 'one', 'clip_plan': {'start_seconds': 0, 'duration_seconds': 60},
               'source_excerpt': 'Build cash reserves before hiring staff and expanding your business. Review the plan.'}
    contained = {'source_id': 'one', 'clip_plan': {'start_seconds': 20, 'duration_seconds': 20},
                 'source_excerpt': 'A different description does not make the same footage new.'}
    repeat = {'source_id': 'two', 'clip_plan': {'start_seconds': 100, 'duration_seconds': 30},
              'source_excerpt': 'A useful rule: build cash reserves before hiring staff and expanding your business.'}
    assert 'timestamp_overlap' in compare_moments(contained, earlier)['reasons']
    assert 'repeated_quote' in compare_moments(repeat, earlier)['reasons']


def test_semantic_dedup_requires_matching_embedding_provenance():
    from clipping.selection.dedup import compare_moments
    first = {'source_id': 'a', 'source_excerpt': 'First viewpoint.',
             'embedding': [1.0, 0.0], 'embedding_model': 'local-v1'}
    second = {'source_id': 'b', 'source_excerpt': 'A distinct phrasing.',
              'embedding': [.99, .01], 'embedding_model': 'local-v1'}
    assert 'semantic_similarity' in compare_moments(first, second)['reasons']
    second['embedding_model'] = 'another-space'
    report = compare_moments(first, second)
    assert not report['duplicate'] and report['semantic_similarity'] is None


def test_strict_source_selection_applies_configured_quality_floor():
    from app.core.config import load_settings
    from clipping.sections import select_moments
    settings = load_settings(environ={})
    settings.selection.minimum_score = .99
    source = {'title': '', 'duration': 1800, 'segments': [
        {'start': 10, 'end': 45, 'text': 'Practice improves judgment. Review decisions regularly.'}]}
    with pytest.raises(ValueError, match='usable'):
        select_moments(source, 1, 35, strict=True, settings=settings)


def test_configured_text_threshold_controls_source_diversity_gate():
    from app.core.config import load_settings
    from clipping.sections import select_moments
    settings = load_settings(environ={})
    settings.dedup.transcript_similarity_threshold = 1.0
    settings.dedup.quote_words = 100
    source = {'title': 'Business reserves', 'duration': 1800, 'segments': [
        {'start': 10, 'end': 45, 'text': 'Cash flow protects three working reserves before hiring staff. Build a plan.'},
        {'start': 100, 'end': 135, 'text': 'Cash flow protects three working reserves before hiring managers. Build a plan.'}]}
    assert len(select_moments(source, 2, 35, strict=True, settings=settings)) == 2
