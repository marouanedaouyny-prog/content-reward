from pathlib import Path

import pytest


def candidate(**quality):
    return {'clip_plan': {'start_seconds': 0, 'duration_seconds': 35},
            'quality': {'completed_ending': True, 'speech_ratio': .9, 'largest_speech_gap': .3, **quality}}


def test_pre_render_rejects_promotions_incomplete_thoughts_and_silence():
    from clipping.quality.validation import validate_candidate
    assert validate_candidate(candidate()).passed
    for changes in [{'promotional': True}, {'completed_ending': False},
                    {'mid_sentence_opening': True}, {'largest_speech_gap': 10}, {'speech_ratio': .1}]:
        report = validate_candidate(candidate(**changes))
        assert not report.passed and report.violations


@pytest.mark.parametrize('changes', [
    {'quality': {'ending_question': True}},
    {'transcript_features': {'ending_question': True}},
    {'source_excerpt': 'The manager disciplined a player. What would that do to your teammates?'},
])
def test_pre_render_rejects_unanswered_questions_even_when_ending_is_punctuated(changes):
    from clipping.quality.validation import validate_candidate
    moment = candidate()
    moment.update({key: value for key, value in changes.items() if key != 'quality'})
    moment['quality'].update(changes.get('quality', {}))
    report = validate_candidate(moment)
    assert not report.passed
    assert 'answered_ending' in report.violations


@pytest.mark.parametrize('text', [
    "He hasn't spoken since he left Manchester United. He's working in the Netherlands now.",
    "We've got another voice note. This one's from Jacob. I've got loads of respect for Tennog.",
])
def test_pre_render_rechecks_transcript_structure_when_saved_flags_are_stale(text):
    from clipping.quality.validation import validate_candidate
    report = validate_candidate({**candidate(), 'source_excerpt': text})
    assert not report.passed


def test_strict_production_requires_explicit_safety_flags_and_source_text():
    from clipping.quality.validation import validate_candidate
    sparse = candidate()
    assert validate_candidate(sparse).passed
    assert not validate_candidate(sparse, strict=True).passed
    complete = {**sparse, 'source_excerpt': 'A team needs a clear plan. Assign one owner to every decision.'}
    complete['quality'] = {**sparse['quality'], **dict.fromkeys((
        'ending_question', 'filler_opening', 'context_dependent_opening', 'mid_sentence_opening',
        'promotional', 'intro_or_outro', 'host_meta_setup'), False)}
    assert validate_candidate(complete, strict=True).passed
    complete['quality'].pop('host_meta_setup')
    assert not validate_candidate(complete, strict=True).passed


def test_strict_production_accepts_explicit_ending_evidence_from_saved_transcript_features():
    from clipping.quality.validation import validate_candidate
    moment = candidate(**dict.fromkeys((
        'filler_opening', 'context_dependent_opening', 'mid_sentence_opening',
        'promotional', 'intro_or_outro', 'host_meta_setup'), False))
    moment.update(source_excerpt='A team needs a clear plan. Assign one owner to every decision.',
                  transcript_features={'ending_question': False})
    assert validate_candidate(moment, strict=True).passed


@pytest.mark.parametrize(('text', 'violation'), [
    ('I believed I could be successful when I was younger, but let me tell you what.', 'no_pending_payoff'),
    ('Planning protects the business. Here\u2019s the thing.\u201d', 'no_pending_payoff'),
    ('Yes, sir. I agree. We should do a fight at the White House.', 'no_filler_or_weak_opening'),
    ('>> [laughter] Okay, a business needs three complementary skills.', 'no_filler_or_weak_opening'),
])
def test_strict_candidate_rechecks_current_boundary_policy_when_saved_flags_are_stale(text, violation):
    from clipping.quality.validation import validate_candidate
    moment = candidate(**dict.fromkeys((
        'ending_question', 'filler_opening', 'context_dependent_opening', 'mid_sentence_opening',
        'promotional', 'intro_or_outro', 'host_meta_setup'), False))
    moment['source_excerpt'] = text
    assert moment['quality']['completed_ending'] is True
    assert moment['quality']['filler_opening'] is False
    result = validate_candidate(moment, strict=True)
    assert not result.passed and violation in result.violations


@pytest.mark.parametrize('text', [
    'I believed a written plan could protect payroll, but let me tell you what. Cash reserves made the difference.',
    'Why does a business need cash reserves? Late invoices can leave payroll unfunded.',
    'A written plan protects payroll. Assign one owner to every payment.',
])
def test_strict_boundary_recheck_keeps_completed_payoffs_and_answered_questions(text):
    from clipping.quality.validation import validate_candidate
    moment = candidate(**dict.fromkeys((
        'ending_question', 'filler_opening', 'context_dependent_opening', 'mid_sentence_opening',
        'promotional', 'intro_or_outro', 'host_meta_setup'), False))
    moment['source_excerpt'] = text
    assert validate_candidate(moment, strict=True).passed


@pytest.mark.parametrize('analysis, rate, passed', [
    ('lavfi.astats.Overall.RMS_level=-20\n', '25/1', True),
    ('lavfi.astats.Overall.RMS_level=-20\nlavfi.black_start=1\nlavfi.black_end=3\n', '25/1', False),
    ('lavfi.astats.Overall.RMS_level=-inf\n', '25/1', False),
    ('lavfi.astats.Overall.RMS_level=-20\n', '1/1', False),
    ('lavfi.astats.Overall.RMS_level=-20\nlavfi.silence_start=0\nlavfi.silence_end=4\n', '25/1', False),
])
def test_export_qc_enforces_black_silence_audio_and_fps(tmp_path, analysis, rate, passed):
    from clipping.quality.validation import validate_media
    path = tmp_path / 'clip.mp4'
    path.write_bytes(b'video' * 1000)
    srt = tmp_path / 'captions.srt'
    srt.write_text('1\n00:00:00,000 --> 00:00:05,000\nComplete thought.\n')
    info = {'format': {'duration': '5'}, 'streams': [
        {'codec_type': 'video', 'width': 1080, 'height': 1920, 'avg_frame_rate': rate},
        {'codec_type': 'audio'}]}
    report = validate_media(path, srt, duration=5, info=info, analysis=analysis)
    assert report.passed is passed
    assert report.model_dump()['score'] >= 0


def test_export_review_rejects_detected_black_frames(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location('review_fixture', Path('tests/clipping/test_clip_review.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine, job = module.fixture(tmp_path, monkeypatch)
    from clipping import media
    from clipping.clip_review import verify_export
    monkeypatch.setattr(media, 'command', lambda *args, **kwargs:
                        'lavfi.astats.Overall.RMS_level=-20\nlavfi.black_start=1\nlavfi.black_end=3\n')
    with pytest.raises(ValueError, match='black'):
        verify_export(engine, job, tmp_path / 'review')


def test_decode_uses_strict_error_detection(monkeypatch):
    from clipping.quality.validation import analyze
    from clipping import media
    captured = []
    monkeypatch.setattr(media, 'command', lambda args, **kwargs: captured.append(args) or '')
    analyze(Path('clip.mp4'))
    assert '-xerror' in captured[0]
    assert captured[0][captured[0].index('-err_detect') + 1] == 'explode'
