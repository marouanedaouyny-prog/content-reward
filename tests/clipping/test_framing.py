"""Speaker-focus framing: reliability gates, fallback and render wiring."""

import json
import shutil

import pytest

from clipping.framing import analyze, crop_rect, _cascade_unavailable


def stable_faces(count=10, center=(0.5, 0.4), height=0.15):
    return [(center[0], center[1])] * count, [height] * count


def test_crop_math_produces_an_even_clamped_portrait_rect():
    centers, heights = stable_faces()
    rect, reason = crop_rect(1920, 1080, centers, heights, '9:16')
    assert reason == 'stable_face_crop'
    x, y, width, height = rect
    assert width % 2 == height % 2 == 0
    assert 0 <= x and x + width <= 1920 and 0 <= y and y + height <= 1080
    assert width / height == pytest.approx(9 / 16, abs=.02)
    assert height >= 1080 * 0.55  # Keeps context around the speaker.


def test_crop_math_refuses_unstable_or_unfit_faces():
    drifting = [(0.3 + index * .06, 0.4) for index in range(10)]
    assert crop_rect(1920, 1080, drifting, [0.15] * 10, '9:16')[1] == 'face_center_too_unstable'
    assert crop_rect(1920, 1080, *stable_faces(height=0.02), '9:16')[1] == 'face_size_outside_crop_range'
    assert crop_rect(1920, 1080, *stable_faces(height=0.8), '9:16')[1] == 'face_size_outside_crop_range'
    assert crop_rect(1920, 1080, [], [], '9:16')[1] == 'no_face_evidence'
    assert crop_rect(1920, 1080, *stable_faces(), '7:5')[1] == 'no_face_evidence'


def test_missing_opencv_reports_an_honest_reason(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == 'cv2':
            raise ImportError('blocked for test')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', blocked)
    report = analyze(tmp_path / 'missing.mp4', 0, 5)
    assert report['crop'] is None and report['reason'] == 'opencv_unavailable'


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe') or _cascade_unavailable(),
                    reason='FFmpeg and OpenCV CascadeClassifier required')
def test_frames_without_faces_fall_back_to_fit(tmp_path):
    from clipping import framing as framing_module
    if framing_module._cascade_unavailable():
        pytest.skip('OpenCV CascadeClassifier not available')
    source = tmp_path / 'source.mp4'
    from clipping import media
    media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25', '-t', '4',
        '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast', str(source)])
    report = analyze(source, 0, 4)
    assert report['crop'] is None
    assert report['reason'] == 'no_stable_face_detected'
    assert report['frames_sampled'] > 0 and report['face_coverage'] == 0


@pytest.fixture
def render_fixture(tmp_path, monkeypatch):
    from clipping import media
    folder = tmp_path / 'render'
    folder.mkdir()
    captured = {}
    selected = {}

    def command(args, **kwargs):
        captured['args'] = list(args)
        if '-frames:v' in args:
            from pathlib import Path
            Path(args[-1]).write_bytes(b'REVIEW FRAME')
        else:
            (folder / 'clip.mp4').write_bytes(b'fixture' * 300)

    def probe(path):
        return {'streams': [{'codec_type': 'video', 'codec_name': 'h264',
                             'width': 1080, 'height': 1920},
                            {'codec_type': 'audio', 'codec_name': 'aac'}],
                'format': {'duration': selected.get('duration', 1)}}

    monkeypatch.setattr(media, 'command', command)
    monkeypatch.setattr(media, 'probe', probe)
    from clipping.quality.validation import QualityResult
    monkeypatch.setattr('clipping.quality.validation.validate_media',
                        lambda *args, **kwargs: QualityResult(passed=True, score=100,
                                                              checks={'fixture_only': True}))

    def render(start=0, duration=2, **payload):
        selected['duration'] = duration
        source = tmp_path / 'source.mp4'
        source.write_bytes(b'SOURCE')
        (tmp_path / 'transcript.json').write_text(json.dumps({'segments': [
            {'start': 0, 'end': 2, 'text': 'A complete point.', 'words': [
                {'start': 0, 'end': 1, 'word': 'A complete'},
                {'start': 1, 'end': 2, 'word': ' point.'}]}]}), encoding='utf-8')
        return media.render({'clip_plan': {'start_seconds': start, 'duration_seconds': duration,
                                           'aspect_ratio': '9:16'}, **payload},
                            {'source_path': 'source.mp4', 'source_duration': 2,
                             'transcript_path': 'transcript.json'}, folder, tmp_path), captured

    return render


def test_reliable_detection_uses_a_speaker_crop(render_fixture, monkeypatch):
    from clipping import framing as framing_module
    monkeypatch.setattr(framing_module, 'analyze', lambda *args, **kwargs:
                        {'crop': [100, 200, 540, 960], 'reason': 'stable_face_crop',
                         'frames_sampled': 10, 'frames_with_face': 10, 'face_coverage': 1.0})
    result, captured = render_fixture(framing_mode='speaker-focus')
    assert result['framing_mode'] == 'speaker-focus'
    assert 'crop=540:960:100:200' in ' '.join(captured['args'])
    assert 'framing_fallback' not in result


def test_unreliable_detection_falls_back_to_fit_and_records_the_reason(render_fixture, monkeypatch):
    from clipping import framing as framing_module
    monkeypatch.setattr(framing_module, 'analyze', lambda *args, **kwargs:
                        {'crop': None, 'reason': 'no_stable_face_detected',
                         'frames_sampled': 10, 'frames_with_face': 2, 'face_coverage': 0.2})
    result, captured = render_fixture(framing_mode='speaker-focus', caption_style='classic')
    assert result['framing_mode'] == 'fit'
    assert result['framing_fallback'] == {'requested': 'speaker-focus', 'used': 'fit',
                                          'reason': 'no_stable_face_detected'}
    assert 'overlay=' in ' '.join(captured['args'])  # The blurred fit graph was used.


def test_default_framing_does_not_run_face_detection(render_fixture, monkeypatch):
    from clipping import framing as framing_module

    def forbidden(*args, **kwargs):
        raise AssertionError('face detection must not run for the default framing')

    monkeypatch.setattr(framing_module, 'analyze', forbidden)
    result, _ = render_fixture()
    assert result['framing_mode'] == 'fit'


def test_request_and_controller_accept_speaker_focus():
    from clipping.workflow import validate_request
    from clipping.orchestrator import Config
    request = {'preview_only': True, 'framing_mode': 'speaker-focus',
        'source_url': 'https://www.youtube.com/watch?v=abcdefghijk',
        'campaign': {'title': 'Preview', 'url': 'https://www.youtube.com/watch?v=abcdefghijk',
            'platform': 'youtube', 'rights_notes': 'Local preview', 'rules': 'Local preview'},
        'clip_plan': {'start_seconds': 0, 'duration_seconds': 30, 'aspect_ratio': '9:16'}}
    assert validate_request(request)['framing_mode'] == 'speaker-focus'
    assert Config(framing_mode='speaker-focus').validate() is None
    with pytest.raises(ValueError, match='framing'):
        Config(framing_mode='everywhere').validate()
