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
        {'codec_type': 'video', 'codec_name': 'h264', 'width': 1080, 'height': 1920, 'avg_frame_rate': '25/1'},
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


def test_displayed_zero_duration_insertions_are_checked_against_source_speech(tmp_path, monkeypatch):
    from clipping.captions import cues_for_window
    from clipping.clip_review import verify_export
    engine, job = fixture(tmp_path, monkeypatch)
    job['payload']['source_reference'] = [{'start': 0, 'end': 5, 'text': 'A complete point.'}]
    # Zero-duration tokens are not timed speech evidence but the caption grouper
    # retains them with a neighbor. The displayed result needs its own assessment.
    segment = {'start': 0, 'end': 5, 'text': 'Cosmic geese eat rice A complete point.', 'words': [
        {'start': 0, 'end': 0, 'word': 'Cosmic geese eat rice'},
        {'start': 0, 'end': 1, 'word': ' A'},
        {'start': 1, 'end': 3, 'word': ' complete'},
        {'start': 3, 'end': 5, 'word': ' point.'}]}
    engine.safe_path(job['output']['transcript_path']).write_text(json.dumps({'segments': [segment]}))
    cues = cues_for_window([segment], 0, 5)
    engine.safe_path(job['output']['subtitle_path']).write_text('\n\n'.join(
        f"{index}\n{media.srt_time(cue['start'])} --> {media.srt_time(cue['end'])}\n{cue['text']}"
        for index, cue in enumerate(cues, 1)) + '\n')
    with pytest.raises(ValueError, match='displayed_caption_coverage'):
        verify_export(engine, job, tmp_path / 'review')


def test_missing_source_evidence_is_explicit_in_a_mechanical_review(tmp_path, monkeypatch):
    from clipping.clip_review import verify_export
    engine, job = fixture(tmp_path, monkeypatch)
    report = verify_export(engine, job, tmp_path / 'review')
    assert report['caption_evidence']['evaluated'] is False
    assert report['caption_evidence']['reason'] == 'missing_independent_source_cues'
    assert report['speech_accuracy'] == 'not_verified'


def test_operator_srt_recovery_with_independent_cues_can_complete_export_review(tmp_path, monkeypatch):
    from clipping.clip_review import verify_export
    engine, prepared = fixture(tmp_path, monkeypatch)
    ingest_count = []
    output = prepared['output']

    def ingest(*args):
        ingest_count.append(True)
        return {key: output[key] for key in ('source_path', 'source_sha256', 'synthetic_source')} | {
            'source_duration': 5}

    command = media.command

    def unavailable_inference(args, **kwargs):
        if any(str(argument).endswith('_transcribe.py') for argument in args):
            return json.dumps({'language': 'en', 'segments': []})
        return command(args, **kwargs)

    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(media, 'command', unavailable_inference)
    monkeypatch.setattr(media, 'render', lambda *args: {key: output[key] for key in
        ('clip_path', 'clip_sha256', 'subtitle_path')})
    job = engine.create({'campaign': {'title': 'Recovery test', 'url': 'https://example.com/source',
        'platform': 'youtube', 'rules': 'Local fixture', 'rights_notes': 'Local fixture'},
        'preview_only': True, 'dry_run': False, 'source_path': output['source_path'], 'language': 'en',
        'source_reference': [{'start': 0, 'end': 5, 'text': 'A complete point.'}],
        'clip_plan': output['selected_clip_plan']})
    assert engine.consume_once()
    assert engine.get(job['id'])['status'] == 'awaiting_transcript'
    engine.provide_transcript(job['id'], '1\n00:00:00,000 --> 00:00:05,000\nA complete point.\n')
    assert engine.consume_once()
    recovered = engine.get(job['id'])
    assert recovered['status'] == 'completed'
    assert recovered['output']['transcript_origin'] == 'operator_supplied'
    recovered['output']['selected_clip_plan'] = recovered['payload']['clip_plan']
    report = verify_export(engine, recovered, tmp_path / 'recovered-review')
    assert report['checks']['speech_transcript'] is True
    assert report['checks']['displayed_caption_coverage'] is True
    assert report['transcript_origin'] == 'operator_supplied'
    assert report['speech_accuracy'] == 'not_verified'
    assert report['human_review_required'] is True
    assert any('accuracy' in warning.lower() for warning in report['warnings'])
    assert len(ingest_count) == 1


@pytest.mark.parametrize('evidence', ['missing', 'disagrees', 'practice'])
def test_operator_supplied_origin_requires_independent_supported_real_speech(tmp_path, monkeypatch, evidence):
    from clipping.clip_review import verify_export
    engine, job = fixture(tmp_path, monkeypatch)
    job['output']['transcript_origin'] = 'operator_supplied'
    if evidence != 'missing':
        job['payload']['source_reference'] = [{'start': 0, 'end': 5, 'text':
            'A complete point.' if evidence == 'practice' else 'Entirely different source speech.'}]
    if evidence == 'practice':
        job['payload']['dry_run'] = True
    with pytest.raises(ValueError, match='speech_transcript|caption_coverage'):
        verify_export(engine, job, tmp_path / 'review')


@pytest.mark.parametrize('origin', ['operator_supplied_practice', 'synthetic_practice', 'mock', 'demo',
    'faster_whisper:mock', 'faster_whisper:demo', 'faster_whisper:'])
def test_synthetic_or_mock_origins_cannot_bypass_export_review_with_matching_cues(tmp_path, monkeypatch, origin):
    from clipping.clip_review import verify_export
    engine, job = fixture(tmp_path, monkeypatch)
    job['output']['transcript_origin'] = origin
    job['payload']['source_reference'] = [{'start': 0, 'end': 5, 'text': 'A complete point.'}]
    with pytest.raises(ValueError, match='speech_transcript'):
        verify_export(engine, job, tmp_path / 'review')


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
