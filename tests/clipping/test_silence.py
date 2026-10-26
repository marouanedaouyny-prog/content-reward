"""Silence detection and opt-in removal planning (PRD-GROWTH section 9)."""

import shutil

import pytest

from clipping.silence import detect, plan_removal, remap_cues, time_map


ANALYSIS = ('lavfi.silence_start=2.017\nlavfi.silence_end=3.503\n'
            'lavfi.silence_start=7.0\nlavfi.silence_end=7.2\n'
            'lavfi.silence_start=8.5\nlavfi.silence_end=8.7\n')


def settings_for(tmp_path, monkeypatch, text):
    from app.core.config import load_settings, read_yaml
    path = tmp_path / 'overlay.yaml'
    path.write_text(text, encoding='utf-8')
    # The overlay stays active for the whole test; monkeypatch restores the
    # environment afterwards, so later load_settings() calls still see it.
    monkeypatch.setenv('CONTENT_REWARD_CONFIG', str(path))
    read_yaml.cache_clear()
    return load_settings()


def test_removal_planning_keeps_micro_pauses_and_refuses_mostly_silent_windows():
    assert plan_removal(10, [])['applied'] is False
    refused = plan_removal(10, [(2, 5.5), (7, 9)])
    assert refused['applied'] is False and refused['reason'] == 'too_much_detected_silence'
    all_silence = plan_removal(10, [(0, 9.95)])
    assert all_silence['applied'] is False
    plan = plan_removal(10, [(4.0, 5.5)])
    assert plan['applied'] is True and plan['removed_seconds'] == 1.5
    assert plan['kept'] == [(0.0, 4.0), (5.5, 10)]


def test_gap_smaller_than_the_keep_minimum_is_dropped():
    # Sub-0.1s kept fragments are stitching artifacts, not removable content.
    plan = plan_removal(10, [(0.05, 10)])
    assert plan['applied'] is False or all(finish - begin >= .1
                                           for begin, finish in plan['kept'])


def test_time_map_is_monotonic_and_preserves_cue_text():
    cues = [{'start': 0, 'end': 2, 'text': 'First.'},
            {'start': 4, 'end': 6, 'text': 'Second.'}]
    mapped = remap_cues(cues, [(2.0, 4.0)])
    assert [cue['text'] for cue in mapped] == ['First.', 'Second.']
    assert mapped[1] == {'start': 2.0, 'end': 4.0, 'text': 'Second.'}
    shift = time_map([(2.0, 4.0), (6.0, 7.0)])
    assert shift(1) == 1 and shift(3) == 2 and shift(5) == 3 and shift(8) == 5
    assert all(shift(a) <= shift(b) for a, b in [(0, 1), (1, 3), (3, 5), (5, 8)])


def test_detect_parses_metadata_output_and_keeps_only_long_gaps(tmp_path, monkeypatch):
    from clipping import silence as silence_module
    captured = {}

    def command(args, **kwargs):
        captured['args'] = args
        return ANALYSIS

    monkeypatch.setattr(silence_module.media, 'command', command)
    settings = settings_for(tmp_path, monkeypatch, 'silence: {threshold_db: -35, min_duration_ms: 450}\n')
    gaps = detect(tmp_path / 'section.mp4', 3, 10, settings=settings)
    # Both 0.2s gaps stay as micro-pauses below the configured minimum.
    assert gaps == [(2.017, 3.503)]
    assert 'silencedetect=noise=-35dB:d=0.45' in ' '.join(captured['args'])
    assert 'ametadata=print:file=-' in ' '.join(captured['args'])


def test_detect_clamps_a_trailing_silence_to_the_window_end(tmp_path, monkeypatch):
    from clipping import silence as silence_module
    monkeypatch.setattr(silence_module.media, 'command',
                        lambda args, **kwargs: 'lavfi.silence_start=8.0\n')
    settings = settings_for(tmp_path, monkeypatch, 'silence: {min_duration_ms: 450}\n')
    assert detect(tmp_path / 'section.mp4', 0, 10, settings=settings) == [(8.0, 10)]


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),
                    reason='FFmpeg required')
def test_aggressive_cut_render_removes_detected_silence_and_keeps_captions_synced(tmp_path, monkeypatch):
    import json
    from clipping import media
    source = tmp_path / 'source.mp4'
    media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25',
        '-f', 'lavfi', '-i', 'aevalsrc=sin(2*PI*440*t)*0.8:d=10',
        '-af', "volume=enable='between(t,4,5.5)':volume=0",
        '-t', '10', '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast',
        '-c:a', 'aac', str(source)])

    def segment(start, tokens):
        words = [{'start': start + i * .4, 'end': start + (i + 1) * .4 - .05,
                  'word': (' ' if i else '') + token} for i, token in enumerate(tokens)]
        return {'start': start, 'end': start + len(tokens) * .4,
                'text': ' '.join(tokens), 'words': words}

    segments = [segment(0, 'He made a bold decision that nobody expected.'.split()),
                segment(5.6, 'The market turned the same week.'.split())]
    (tmp_path / 'transcript.json').write_text(json.dumps({'segments': segments}), encoding='utf-8')
    settings_for(tmp_path, monkeypatch, 'silence: {aggressive_cut: true}\n')
    output = {'source_path': 'source.mp4', 'source_duration': 10, 'transcript_path': 'transcript.json'}
    plan = {'start_seconds': 0, 'duration_seconds': 10, 'aspect_ratio': '9:16'}
    folder = tmp_path / 'render'
    folder.mkdir()
    result = media.render({'clip_plan': plan, 'framing_mode': 'fit', 'caption_style': 'colorized'},
                          output, folder, tmp_path)
    removal = result['silence_removal']
    assert removal['applied'] is True and removal['removed_seconds'] > 1
    assert result['render_duration_seconds'] == pytest.approx(10 - removal['removed_seconds'])
    cues = media.parse_srt((tmp_path / result['subtitle_path']).read_text(encoding='utf-8'))
    # Captions after the removed pause shift by the removed duration.
    assert cues[-1]['end'] == pytest.approx(7.95 - removal['removed_seconds'], abs=.02)
    from clipping.workflow import ClippingWorkflow
    from clipping.clip_review import verify_export
    engine = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path)
    job = {'payload': {'dry_run': False}, 'output': {**result, 'selected_clip_plan': plan,
        'synthetic_source': False, 'source_path': 'source.mp4', 'transcript_path': 'transcript.json',
        'source_sha256': media.file_hash(source), 'transcript_origin': 'faster_whisper:en'}}
    review = verify_export(engine, job, tmp_path / 'review')
    assert review['passed'] is True
    assert review['checks']['duration'] is True and review['checks']['subtitle_timing'] is True
    assert review['silence_removal']['applied'] is True


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),
                    reason='FFmpeg required')
def test_default_render_never_removes_silence(tmp_path):
    from clipping import media
    source = tmp_path / 'source.mp4'
    media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25',
        '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=44100', '-t', '2',
        '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast', '-c:a', 'aac', str(source)])
    import json
    segments = [{'start': 0, 'end': 1, 'text': 'Build a business.', 'words': [
        {'start': 0, 'end': .3, 'word': 'Build'}, {'start': .3, 'end': .4, 'word': ' a'},
        {'start': .4, 'end': 1, 'word': ' business.'}]}]
    (tmp_path / 'transcript.json').write_text(json.dumps({'segments': segments}), encoding='utf-8')
    output = {'source_path': 'source.mp4', 'source_duration': 2, 'transcript_path': 'transcript.json'}
    plan = {'start_seconds': 0, 'duration_seconds': 1, 'aspect_ratio': '9:16'}
    folder = tmp_path / 'render'
    folder.mkdir()
    result = media.render({'clip_plan': plan}, output, folder, tmp_path)
    assert 'silence_removal' not in result and 'render_duration_seconds' not in result
