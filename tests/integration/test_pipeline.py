import json
import shutil

import pytest


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_candidate_fake_download_transcription_resume_real_render_and_qc(tmp_path, monkeypatch):
    from clipping import media, sections
    from clipping.clip_review import verify_export
    from clipping.workflow import ClippingWorkflow
    source = {'id': 'abcdefghijk', 'title': 'Strong teams communicate clearly', 'duration': 1800,
              'heatmap': [], 'segments': [
                  {'start': 100, 'end': 110, 'text': 'Strong teams share a clear purpose.'},
                  {'start': 110, 'end': 120, 'text': 'Assign one owner and a deadline to each action.'}]}
    moment = sections.select_moments(source, 1, 20, strict=True)[0]
    assert moment['clip_plan']['duration_seconds'] == 20
    storage = tmp_path / 'storage'
    storage.mkdir()
    bounded = storage / 'selected-section.mp4'
    # Explicit local fake download boundary; no network source is contacted.
    media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-t', '26',
        '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast', '-c:a', 'aac', str(bounded)])
    engine = ClippingWorkflow(tmp_path / 'jobs.db', storage)
    segments = [{**cue, 'start': cue['start'] - 97, 'end': cue['end'] - 97} for cue in source['segments']]
    data = dict(campaign=dict(title='Synthetic integration fixture', url='https://example.com/fixture',
        platform='youtube', rules='Local test only', rights_notes='Generated fixture'),
        source_path=bounded.name, preview_only=True, dry_run=False, language='en',
        source_reference=segments,
        clip_plan={**moment['clip_plan'], 'start_seconds': 3})
    job = engine.create(data)
    counts = {'ingest': 0, 'transcription': 0, 'render': 0}
    real_ingest, real_render = media.ingest, media.render

    def ingest(*args):
        counts['ingest'] += 1
        return real_ingest(*args)

    def transcript(data, output, folder, storage):
        counts['transcription'] += 1
        path = folder / 'transcript.json'
        path.write_text(json.dumps({'segments': segments}), encoding='utf-8')
        return {'transcript_path': path.relative_to(storage).as_posix(),
                'transcript_sha256': media.file_hash(path), 'transcript_origin': 'faster_whisper:en'}

    def render(*args):
        counts['render'] += 1
        if counts['render'] == 1:
            raise ValueError('Simulated render interruption')
        return real_render(*args)

    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(media, 'transcribe', transcript)
    monkeypatch.setattr(media, 'render', render)
    engine.consume_once()
    assert engine.get(job['id'])['status'] == 'failed'
    engine.retry(job['id'])
    engine.consume_once()
    job = engine.get(job['id'])
    assert job['status'] == 'completed', job['error']
    assert counts == {'ingest': 1, 'transcription': 1, 'render': 2}
    output = {**job['output'], 'selected_clip_plan': data['clip_plan']}
    report = verify_export(engine, {**job, 'output': output}, tmp_path / 'review')
    assert report['passed'] and report['checks']['full_decode']
    assert report['independent_source_cues'] and report['human_review_required']
