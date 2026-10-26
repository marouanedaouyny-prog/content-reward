import importlib.util
from pathlib import Path

import pytest

from growth.hook import HookScorer
from growth.quality import MEDIA_GROUPS, completeness, score_quality
from growth.retention import RetentionScorer
from growth.scorer import GrowthScorer

STRONG_TEXT = 'This mistake cost him millions. He thought he was winning until the market turned.'
WEAK_TEXT = 'So basically, today we are going to talk about the update. Well, you know. Um.'


def candidate(**changes):
    base = {'clip_plan': {'start_seconds': 0, 'duration_seconds': 30, 'aspect_ratio': '9:16'},
            'source_excerpt': STRONG_TEXT,
            'transcript_features': {'opening_question': False, 'opening_topic_matches': 1,
                                    'topic_matches': 2, 'ending_question': False,
                                    'words_per_second': 2.5},
            'quality': {'filler_opening': False, 'context_dependent_opening': False,
                        'mid_sentence_opening': False, 'intro_or_outro': False,
                        'host_meta_setup': False, 'completed_ending': True,
                        'promotional': False, 'silence_seconds': 0.2,
                        'largest_speech_gap': 0.3, 'speech_ratio': 0.95}}
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def weak_candidate():
    return candidate(source_excerpt=WEAK_TEXT,
                     transcript_features={'opening_question': False, 'topic_matches': 0,
                                          'ending_question': True, 'words_per_second': 1.0},
                     quality={'filler_opening': True, 'completed_ending': False,
                              'ending_question': True, 'speech_ratio': 0.8,
                              'silence_seconds': 2.0, 'largest_speech_gap': 3.0})


def all_checks(passed=True):
    return {key: passed for keys in MEDIA_GROUPS.values() for key in keys}


def test_hook_scoring_ranks_strong_openings_above_weak_and_labels_markers():
    strong = HookScorer().score(candidate())
    weak = HookScorer().score(weak_candidate())
    assert 0 < weak['value'] < strong['value'] <= 1
    assert strong['hook_type'] == 'bold_statement'
    assert 'bold_statement' in strong['matched']
    assert strong['opening_quality'] == 1.0 and strong['weak_opening'] is False
    assert weak['weak_opening'] is True and weak['opening_quality'] == 0.3
    assert strong['basis'] and 'not verified' in strong['basis']


def test_hook_scoring_detects_questions_and_mid_sentence_starts():
    questioned = HookScorer().score(candidate(
        transcript_features={'opening_question': True, 'topic_matches': 0,
                             'ending_question': False, 'words_per_second': 2.0}))
    assert 'strong_question' in questioned['matched']
    mid_sentence = HookScorer().score(candidate(quality={'mid_sentence_opening': True}))
    assert mid_sentence['opening_quality'] == 0.2
    assert mid_sentence['value'] <= 0.2


def test_hook_scoring_never_invents_evidence():
    neutral = HookScorer().score(candidate(source_excerpt='The teams met on Tuesday afternoon.'))
    assert neutral['hook_type'] == 'neutral' and neutral['matched'] == []
    assert neutral['value'] == 0.5  # Clean opening with no detected hook markers.
    empty = HookScorer().score({})
    assert empty['value'] is None and 'not evaluated' in empty['basis']


def test_missing_opening_text_is_unknown_even_when_other_quality_flags_exist():
    candidate = {'quality': {'completed_ending': True}}
    hook = HookScorer().score(candidate)
    assert hook['value'] is None
    assert hook['opening_quality'] is None


def test_retention_does_not_invent_a_first_sentence_from_an_ending_flag():
    candidate = {'quality': {'completed_ending': True}}
    assert 'strong_first_sentence' not in RetentionScorer().score(candidate)['signals']


def test_standalone_clarity_needs_its_own_flags():
    candidate = {'quality': {'completed_ending': True}}
    report = GrowthScorer().score(candidate)
    assert report['signals']['standalone_clarity']['value'] is None
    assert 'standalone_clarity' in report['missing_signals']


def test_retention_scoring_rewards_payoff_and_penalizes_pauses_and_weak_endings():
    strong = RetentionScorer().score(candidate())
    weak = RetentionScorer().score(weak_candidate())
    assert strong['value'] >= 0.8 and strong['penalties'] == {}
    assert strong['signals']['clear_payoff'] == 1.0
    assert weak['value'] < strong['value']
    assert {'slow_intro', 'long_pauses', 'dead_air', 'weak_ending', 'mid_answer_ending'} <= set(weak['penalties'])
    assert weak['signals']['clear_payoff'] == 0.0
    assert 0 <= weak['value'] <= 1


def test_retention_scoring_reports_missing_evidence_instead_of_inventing_it():
    report = RetentionScorer().score({})
    assert report['value'] is None
    assert report['signals'] == {} and report['missing_signals']


def test_retention_scoring_detects_repeated_sentences():
    repeated = candidate(source_excerpt='The deadline beats motivation. The deadline beats motivation. '
                                        'Assign one owner and finish the work.')
    assert RetentionScorer().score(repeated)['penalties'].get('repetition') == 0.10


def test_growth_score_uses_configured_weights_and_full_evidence():
    from app.core.config import load_settings
    settings = load_settings(environ={})
    report = GrowthScorer(settings).score(candidate(), keywords=['business'])
    assert sum(settings.growth_scoring.model_dump().values()) == pytest.approx(1)
    assert 0 <= report['score'] <= 1 and report['missing_signals'] == []
    assert set(report['signals']) == set(settings.growth_scoring.model_dump())
    assert report['weights'] == settings.growth_scoring.model_dump()
    assert report['completeness'] == 1.0
    assert report['signals']['niche_relevance']['value'] == 1.0


def test_growth_score_reports_missing_niche_keywords_and_empty_candidates():
    scorer = GrowthScorer()
    without_keywords = scorer.score(candidate())
    assert 'niche_relevance' in without_keywords['missing_signals']
    assert without_keywords['evidence_coverage'] < 1
    empty = scorer.score({})
    assert empty['score'] == 0.0 and set(empty['missing_signals']) == set(scorer.weights)


def test_growth_rank_orders_strong_candidates_first():
    scorer = GrowthScorer()
    ranked = scorer.rank([weak_candidate(), candidate()], keywords=['business'])
    assert ranked[0]['source_excerpt'] == STRONG_TEXT


def test_composite_quality_passes_strong_clip_with_mechanical_checks():
    from app.core.config import load_settings
    growth = GrowthScorer().score(candidate(), keywords=['business'])
    report = score_quality(growth=growth, checks=all_checks(), settings=load_settings(environ={}))
    assert report['passed'] is True and report['score'] >= 0.75
    assert report['evaluation'] == 'complete' and report['missing_signals'] == []
    assert report['minimum_score'] == 0.75


def test_composite_quality_rejects_weak_clip_below_threshold():
    growth = {'hook': {'value': 0.10, 'basis': 'fixture'},
              'retention': {'value': 0.30, 'basis': 'fixture'},
              'completeness': 0.20}
    report = score_quality(growth=growth, checks=all_checks())
    assert report['passed'] is False and report['score'] < 0.75


def test_composite_quality_stays_unresolved_with_missing_components():
    report = score_quality(growth=None, checks=all_checks())
    assert report['passed'] is None and report['evaluation'] == 'incomplete_coverage'
    assert 'hook_score' in report['missing_signals']


def test_completeness_requires_completed_transcript_flags():
    assert completeness({'completed_ending': True}) == 1.0
    assert completeness({'completed_ending': False}) == 0.5
    assert completeness({'completed_ending': False, 'context_dependent_opening': True,
                         'mid_sentence_opening': True, 'promotional': True}) == 0.0
    assert completeness({}) is None


def test_planning_attaches_growth_report_to_every_candidate():
    from clipping.planning import suggest_cuts
    segments = [{'start': 0, 'end': 10, 'text': 'This mistake cost him millions in one quarter.'},
                {'start': 10, 'end': 20, 'text': 'He fixed it by assigning one owner to every decision.'},
                {'start': 20, 'end': 35, 'text': 'The lesson is simple: deadlines beat motivation every time.'}]
    choices = suggest_cuts(segments, 35, 20, 15, 35)
    growth = choices[0]['growth']
    assert 0 <= growth['score'] <= 1
    assert isinstance(growth['hook']['value'], (int, float))
    assert isinstance(growth['retention']['value'], (int, float))
    assert 0 <= growth['completeness'] <= 1


def review_fixture(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('review_fixture_growth', Path('tests/clipping/test_clip_review.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.fixture(tmp_path, monkeypatch)


def test_export_review_reports_growth_quality_for_scored_jobs(tmp_path, monkeypatch):
    from clipping.clip_review import verify_export
    engine, job = review_fixture(tmp_path, monkeypatch)
    job['payload']['growth'] = GrowthScorer().score(candidate(), keywords=['business'])
    result = verify_export(engine, job, tmp_path / 'review')
    assert result['growth_quality']['evaluated'] is True
    assert result['growth_quality']['passed'] is True
    assert result['checks']['growth_quality_minimum'] is True


def test_export_review_rejects_growth_quality_below_threshold(tmp_path, monkeypatch):
    from clipping.clip_review import verify_export
    engine, job = review_fixture(tmp_path, monkeypatch)
    job['payload']['growth'] = {'hook': {'value': 0.10, 'basis': 'fixture'},
                                'retention': {'value': 0.30, 'basis': 'fixture'},
                                'completeness': 0.20}
    with pytest.raises(ValueError, match='growth quality score'):
        verify_export(engine, job, tmp_path / 'review')


def test_export_review_without_growth_inputs_skips_the_growth_gate(tmp_path, monkeypatch):
    from clipping.clip_review import verify_export
    engine, job = review_fixture(tmp_path, monkeypatch)
    result = verify_export(engine, job, tmp_path / 'review')
    assert result['growth_quality']['evaluated'] is False
    assert 'growth_quality_minimum' not in result['checks']
