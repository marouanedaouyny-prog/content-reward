import hashlib


def test_changed_transcript_reuses_valid_source_and_invalidates_render(tmp_path):
    from clipping.pipeline.checkpoints import verified_checkpoints
    source, transcript = tmp_path / 'source.mp4', tmp_path / 'transcript.json'
    source.write_bytes(b'source')
    transcript.write_bytes(b'changed')
    output = {'source_path': source.name, 'source_sha256': hashlib.sha256(b'source').hexdigest(),
              'transcript_path': transcript.name, 'transcript_sha256': hashlib.sha256(b'original').hexdigest(),
              'clip_path': 'clip.mp4', 'clip_sha256': 'stale', 'selected_clip_plan': {'start_seconds': 0}}
    verified, invalid = verified_checkpoints(output, tmp_path)
    assert verified['source_path'] == source.name
    assert 'transcript_path' not in verified and 'clip_path' not in verified
    assert 'selected_clip_plan' not in verified
    assert invalid == ['transcription', 'render']


def test_missing_or_outside_source_invalidates_all_dependent_artifacts(tmp_path):
    from clipping.pipeline.checkpoints import verified_checkpoints
    for path in ['missing.mp4', '../outside.mp4']:
        output, invalid = verified_checkpoints({'source_path': path, 'source_sha256': 'old',
            'source_duration': 30, 'transcript_path': 'transcript.json', 'clip_path': 'clip.mp4'}, tmp_path)
        assert not any(key in output for key in ['source_path', 'source_duration', 'transcript_path', 'clip_path'])
        assert 'source_ingest' in invalid


def test_legacy_valid_artifact_receives_hash_without_reprocessing(tmp_path):
    from clipping.pipeline.checkpoints import verified_checkpoints
    path = tmp_path / 'transcript.json'
    path.write_text('{"segments": []}')
    output, invalid = verified_checkpoints({'transcript_path': path.name}, tmp_path)
    assert output['transcript_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert invalid == []
