import json

import pytest

from clipping.workflow import ClippingWorkflow


@pytest.fixture
def workflow(tmp_path):
    return lambda: ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')


def test_ishowspeed_preview_queues_with_no_choices_and_reuses_saved_run(workflow):
    engine = workflow()
    assert hasattr(engine, 'create_automatic_preview'), 'Automatic preview intake is missing'
    job = engine.create_automatic_preview()
    assert job['status'] == 'queued'
    assert job['waiting_step'] is None
    assert job['payload']['source_url'] == 'https://www.youtube.com/watch?v=Uv1PyE8J38w'
    assert job['payload']['preview_only'] is True
    assert job['payload']['dry_run'] is False
    assert job['payload']['auto_clip'] is True
    assert job['payload']['clip_plan']['aspect_ratio'] == '9:16'
    assert job['payload']['language'] == 'en'
    assert engine.create_automatic_preview()['id'] == job['id']


def test_preview_finishes_without_approvals_or_publication(workflow, monkeypatch):
    engine = workflow()
    assert hasattr(engine, 'create_automatic_preview'), 'Automatic preview intake is missing'
    job = engine.create_automatic_preview()
    from clipping import media
    from clipping import planning
    monkeypatch.setattr(media, 'ingest', lambda *args: {
        'source_path': 'source.mp4', 'source_duration': 30, 'synthetic_source': False})
    monkeypatch.setattr(media, 'transcribe', lambda *args: {
        'transcript_path': 'transcript.json', 'transcript_origin': 'test_boundary'})
    monkeypatch.setattr(planning, 'prepare_clip_plan', lambda *args: {
        'selected_clip_plan': {'start_seconds': 0, 'duration_seconds': 30, 'aspect_ratio': '9:16'},
        'clip_suggestions': [{'caption': 'An automatic caption'}]})
    monkeypatch.setattr(media, 'render', lambda *args: {'clip_path': 'clip.mp4', 'clip_sha256': 'test_hash'})
    assert engine.consume_once()
    completed = engine.get(job['id'])
    assert completed['status'] == 'completed'
    assert completed['current_step'] == 'preview_complete'
    assert completed['output']['preview_only'] is True
    assert 'approvals' not in completed['output']
    assert 'publication' not in completed['output']
    assert 'submission' not in completed['output']
    package = json.loads(engine.artifact(job['id'], 'package').read_text(encoding='utf-8'))
    assert package['preview_only'] is True
    assert package['caption'] == 'An automatic caption'
    assert 'Publish' not in package['instructions']
    with pytest.raises(ValueError, match='not waiting for publication'):
        engine.record_publication(job['id'], 'https://youtu.be/Uv1PyE8J38w', True, '2026-10-08T00:00:00Z')


def test_automatic_preview_does_not_turn_into_a_fake_video_under_dry_run(workflow, monkeypatch):
    engine = workflow()
    assert hasattr(engine, 'create_automatic_preview'), 'Automatic preview intake is missing'
    monkeypatch.setenv('DRY_RUN', 'true')
    with pytest.raises(ValueError, match='DRY_RUN'):
        engine.create_automatic_preview()


def test_temporary_download_failure_retries_at_saved_times_then_requires_manual_resume(workflow, monkeypatch):
    from clipping import media
    from clipping import workflow as module
    assert hasattr(media, 'SourceUnavailable'), 'Transient source failure classification is missing'
    engine = workflow()
    monkeypatch.setattr(module, 'utcnow', lambda: '2026-10-08T10:00:00+00:00')
    job = engine.create_automatic_preview()

    def unavailable(*args):
        raise media.SourceUnavailable('Source connection temporarily unavailable')

    monkeypatch.setattr(media, 'ingest', unavailable)
    for attempt in range(1, 3):
        assert engine.consume_once()
        waiting = engine.get(job['id'])
        assert waiting['status'] == 'retry_scheduled'
        retry = waiting['output']['automation_retry']
        assert retry['failed_attempts'] == attempt
        assert retry['next_attempt_at'] > module.utcnow()
        restarted = ClippingWorkflow(engine.database, engine.storage)
        assert not restarted.consume_once(), 'A restart must not bypass retry backoff'
        monkeypatch.setattr(module, 'utcnow', lambda due=retry['next_attempt_at']: due)
        engine = restarted
    assert engine.consume_once()
    failed = engine.get(job['id'])
    assert failed['status'] == 'failed'
    assert failed['output']['automation_retry']['failed_attempts'] == 3
    assert failed['output']['automation_retry']['maximum_attempts'] == 3
    assert failed['output']['automation_retry']['next_attempt_at'] is None
    assert not engine.consume_once()


def test_kill_switch_and_cancellation_stop_automatic_previews(workflow, monkeypatch):
    engine = workflow()
    job = engine.create_automatic_preview()
    monkeypatch.setenv('KILL_SWITCH', 'true')
    assert not engine.consume_once()
    assert engine.get(job['id'])['status'] == 'queued'
    assert engine.cancel(job['id'])['status'] == 'cancelled'
    monkeypatch.delenv('KILL_SWITCH')
    assert not engine.consume_once()


def test_automatic_downloads_are_bounded_and_transient_errors_are_classified(workflow, monkeypatch):
    from clipping import media
    assert hasattr(media, 'SourceUnavailable'), 'Transient source failure classification is missing'
    engine = workflow()
    data = engine.create_automatic_preview()['payload']
    folder = engine.storage / 'source-test'
    folder.mkdir()
    calls = []

    def download(args, **kwargs):
        calls.append((args, kwargs))
        raise ValueError('Unable to connect to proxy: WinError 10061')

    monkeypatch.setattr(media, 'command', download)
    with pytest.raises(media.SourceUnavailable):
        media.ingest(data, {}, folder, engine.storage)
    args, kwargs = calls[0]
    assert 900 <= kwargs['timeout'] <= 1800
    assert '--socket-timeout' in args and '--no-playlist' in args
    assert '--retries' in args and '--ignore-config' in args
    assert args[args.index('--fragment-retries') + 1] == '5'
    assert '--abort-on-unavailable-fragments' in args


def test_operator_retry_after_permanent_failure_resumes_the_same_job(workflow, monkeypatch):
    from clipping import media
    engine = workflow()
    job = engine.create_automatic_preview()

    def unavailable(*args):
        raise ValueError('This video is unavailable')

    monkeypatch.setattr(media, 'ingest', unavailable)
    assert engine.consume_once()
    current = engine.get(job['id'])
    assert current['status'] == 'failed'
    restarted = engine.create_automatic_preview()
    assert restarted['id'] == job['id']
    assert restarted['status'] == 'queued'
    assert not restarted['output'].get('automation_retry')


def test_automatic_preview_renders_real_mp4_without_a_review_click(workflow, monkeypatch):
    import shutil
    from clipping import media
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg required')
    engine = workflow()
    fixture = engine.storage / 'fixtures'
    fixture.mkdir()
    media.ingest({'dry_run': True, 'auto_clip': True, 'clip_plan': {
        'start_seconds': 0, 'duration_seconds': 5}}, {}, fixture, engine.storage)
    ingest, transcribe = media.ingest, media.transcribe

    def fixture_acquisition(data, output, folder, storage):
        return ingest({**data, 'source_url': None, 'source_path': 'fixtures/source.mp4'}, output, folder, storage)

    def fixture_transcript(data, output, folder, storage):
        return transcribe({**data, 'transcript_srt':
            '1\n00:00:00,000 --> 00:00:02,000\nA labeled test fixture.\n\n'
            '2\n00:00:02,000 --> 00:00:05,000\nVerify the automatic preview.\n'}, output, folder, storage)

    monkeypatch.setattr(media, 'ingest', fixture_acquisition)
    monkeypatch.setattr(media, 'transcribe', fixture_transcript)
    job = engine.create_automatic_preview()
    assert engine.consume_once()
    completed = engine.get(job['id'])
    assert completed['status'] == 'completed', completed['error']
    assert completed['output']['preview_only'] is True
    assert all(completed['output']['quality']['checks'].values())
    assert media.probe(engine.artifact(job['id'], 'clip'))['streams'][0]['codec_name'] == 'h264'
    assert engine.artifact(job['id'], 'subtitles').is_file()
    assert not completed['output'].get('approvals')


def test_source_deadline_stops_downloader_children(tmp_path):
    import subprocess
    import sys
    import time
    from clipping import media
    folder = tmp_path
    started, orphan = (folder / 'started').resolve(), (folder / 'orphan').resolve()
    child = f'from pathlib import Path; import time; time.sleep(5); Path({str(orphan)!r}).write_text("orphan")'
    parent = (f'import subprocess,sys,time; from pathlib import Path; '
              f'subprocess.Popen([sys.executable,"-c",{child!r}], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); '
              f'Path({str(started)!r}).write_text("started"); time.sleep(12)')
    with pytest.raises(subprocess.TimeoutExpired):
        # Leave room for both Python launchers to start on a loaded Windows host.
        media.command([sys.executable, '-c', parent], timeout=3, kill_tree=True)
    assert started.is_file(), 'The child-process test did not start'
    time.sleep(5.2)
    assert not orphan.exists(), 'A downloader child survived its deadline'


@pytest.mark.asyncio
async def test_empty_input_automation_api_queues_real_preview(workflow, monkeypatch):
    import httpx
    from clipping.app import app
    engine = workflow()
    monkeypatch.setenv('CLIPPING_DATABASE', str(engine.database))
    monkeypatch.setenv('CLIPPING_STORAGE', str(engine.storage))
    monkeypatch.setattr(ClippingWorkflow, 'consume_once', lambda self: False)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver'
    ) as client:
        endpoint = '/api/v1/clipping/automations/ishowspeed/runs'
        response = await client.post(endpoint)
        assert response.status_code == 202, response.text
        job = response.json()
        assert job['waiting_step'] is None and job['status'] == 'queued'
        assert (await client.post(endpoint, json={})).json()['id'] == job['id']
        assert (await client.post(endpoint, json={'source_url': 'https://example.com'})).status_code == 422
        assert (await client.post(endpoint, headers={'Origin': 'https://untrusted.example'})).status_code == 403


@pytest.mark.asyncio
async def test_startup_automation_enqueues_a_preview_without_an_api_call(workflow, monkeypatch):
    from clipping.app import app
    engine = workflow()
    monkeypatch.setenv('CLIPPING_DATABASE', str(engine.database))
    monkeypatch.setenv('CLIPPING_STORAGE', str(engine.storage))
    monkeypatch.setenv('CLIPPING_AUTOMATION', 'ishowspeed')
    monkeypatch.setattr(ClippingWorkflow, 'consume_once', lambda self: False)
    async with app.router.lifespan_context(app):
        jobs = app.state.workflow.list()
        assert len(jobs) == 1, 'The startup preset did not enqueue a preview'
        assert jobs[0]['status'] == 'queued'
        assert jobs[0]['payload']['preview_only'] is True
