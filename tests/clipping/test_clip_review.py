import json
from pathlib import Path

import pytest

from clipping import media
from clipping.workflow import ClippingWorkflow


def fixture(tmp_path, monkeypatch):
    engine = ClippingWorkflow(tmp_path / 'workflow.db', tmp_path / 'media')
    folder = engine.storage / 'fixture'
    folder.mkdir()
    clip = folder / 'clip.mp4'
    clip.write_bytes(b'TEST EXPORT' * 500)
    (folder / 'source.mp4').write_bytes(b'TEST SOURCE')
    (folder / 'transcript.json').write_text(json.dumps({'segments': [
        {'start': 0, 'end': 5, 'text': 'A complete point.'}]}))
    (folder / 'subtitles.srt').write_text('1\n00:00:00,000 --> 00:00:05,000\nA complete point.\n')
    job = {'payload': {'dry_run': False}, 'output': {
        'clip_path': 'fixture/clip.mp4', 'clip_sha256': media.file_hash(clip),
        'subtitle_path': 'fixture/subtitles.srt', 'transcript_path': 'fixture/transcript.json',
        'synthetic_source': False, 'source_duration': 1800,
        'source_path': 'fixture/source.mp4', 'source_sha256': media.file_hash(folder / 'source.mp4'),
        'transcript_origin': 'faster_whisper:en',
        'selected_clip_plan': {'start_seconds': 0, 'duration_seconds': 5, 'aspect_ratio': '9:16'}}}
    monkeypatch.setattr(media, 'probe', lambda _: {'format': {'duration': '5'}, 'streams': [
        {'codec_type': 'video', 'codec_name': 'h264', 'width': 1080, 'height': 1920},
        {'codec_type': 'audio', 'codec_name': 'aac'}]})

    def analyze(args, **kwargs):
        if '-frames:v' in args:
            Path(args[-1]).write_bytes(b'REVIEW FRAME')
        return 'lavfi.astats.Overall.RMS_level=-20.5\n'

    monkeypatch.setattr(media, 'command', analyze)
    return engine, job


def test_export_review_checks_files_and_keeps_subjective_review_explicit(tmp_path, monkeypatch):
    from clipping.clip_review import verify_export
    engine, job = fixture(tmp_path, monkeypatch)
    result = verify_export(engine, job, tmp_path / 'review')
    assert all(result['checks'].values())
    assert result['human_review_required'] is True
    assert result['speech_accuracy'] == 'not_verified'
    assert len(result['frames']) == 5


def test_saved_asr_and_matching_subtitles_must_also_match_source_speech(tmp_path, monkeypatch):
    from clipping.clip_review import verify_export
    engine, job = fixture(tmp_path, monkeypatch)
    job['payload']['source_reference'] = [{'start': 0, 'end': 5, 'text': 'A complete point.'}]
    assert verify_export(engine, job, tmp_path / 'good-review')['checks']['spoken_caption_coverage'] is True
    engine.safe_path(job['output']['transcript_path']).write_text(json.dumps({'segments': [
        {'start': 0, 'end': 5, 'text': 'One.'}]}))
    engine.safe_path(job['output']['subtitle_path']).write_text('1\n00:00:00,000 --> 00:00:05,000\nOne.\n')
    with pytest.raises(ValueError, match='spoken_caption_coverage'):
        verify_export(engine, job, tmp_path / 'bad-review')


@pytest.mark.parametrize('problem', ['changed_clip', 'changed_source', 'wrong_subtitles', 'paragraph', 'silent', 'synthetic'])
def test_export_review_rejects_unreliable_outputs(tmp_path, monkeypatch, problem):
    from clipping.clip_review import verify_export
    engine, job = fixture(tmp_path, monkeypatch)
    if problem == 'changed_clip':
        engine.safe_path(job['output']['clip_path']).write_bytes(b'changed')
    elif problem == 'changed_source':
        engine.safe_path(job['output']['source_path']).write_bytes(b'changed')
    elif problem == 'wrong_subtitles':
        engine.safe_path(job['output']['subtitle_path']).write_text(
            '1\n00:00:00,000 --> 00:00:05,000\nUnrelated invented text.\n')
    elif problem == 'paragraph':
        engine.safe_path(job['output']['subtitle_path']).write_text(
            '1\n00:00:00,000 --> 00:00:05,000\nA\ncomplete\npoint.\n')
    elif problem == 'silent':
        monkeypatch.setattr(media, 'command', lambda *args, **kwargs:
                            'lavfi.astats.Overall.RMS_level=-inf\n')
    else:
        job['output']['synthetic_source'] = True
    with pytest.raises(ValueError, match='review'):
        verify_export(engine, job, tmp_path / 'review')
