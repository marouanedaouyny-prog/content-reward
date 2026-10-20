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
