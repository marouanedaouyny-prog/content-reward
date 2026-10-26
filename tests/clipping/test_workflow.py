import importlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp('workflow')


def engine(tmp_path):
    assert Path('clipping/workflow.py').exists(), 'Clipping runtime is missing'
    module = importlib.import_module('clipping.workflow')
    return module.ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')


def request(**changes):
    data = {
        'campaign': {'title': 'Software demo', 'url': 'https://contentrewards.com/discover',
                     'platform': 'youtube', 'rights_notes': 'Brand supplied this source for clipping.',
                     'rules': 'Vertical clips with accurate subtitles.', 'experience': 'current'},
        'source_url': 'https://example.com/approved.mp4',
        'clip_plan': {'start_seconds': 0, 'duration_seconds': 5, 'aspect_ratio': '1:1'},
        'dry_run': True,
    }
    return {**data, **changes}


def approve(workflow, job):
    return workflow.approve(job['id'], job['waiting_step'], job['approval_fingerprint'], True)


def test_no_work_before_campaign_approval_and_wrong_gate_rejected(tmp_path):
    workflow = engine(tmp_path)
    job = workflow.create(request())
    assert job['status'] == 'awaiting_campaign_approval'
    assert not workflow.consume_once()
    with pytest.raises(ValueError, match='waiting step'):
        workflow.approve(job['id'], 'clip_review', job['approval_fingerprint'], True)
    assert not list((tmp_path / 'storage').rglob('*.mp4'))


def test_idempotency_survives_restart_and_rejects_changed_inputs(tmp_path):
    workflow = engine(tmp_path)
    first = workflow.create(request(), 'campaign-source-variant')
    second = engine(tmp_path).create(request(), 'campaign-source-variant')
    assert first['id'] == second['id']
    with pytest.raises(ValueError, match='different input'):
        workflow.create(request(caption='Different caption'), 'campaign-source-variant')
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: workflow.create(request())['id'], range(8)))
    assert len(set(ids)) == 1


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_real_dry_run_render_approval_restart_and_no_fake_publication(tmp_path, monkeypatch):
    workflow = engine(tmp_path)
    job = workflow.create(request())
    approve(workflow, job)
    assert workflow.consume_once()
    job = workflow.get(job['id'])
    assert job['status'] == 'awaiting_clip_approval', job
    clip = workflow.artifact(job['id'], 'clip')
    assert clip.exists()
    probe = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(clip)], text=True))
    video = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
    assert (video['width'], video['height']) == (1080, 1080)
    workflow = engine(tmp_path)
    approve(workflow, workflow.get(job['id']))
    assert workflow.consume_once()
    complete = workflow.get(job['id'])
    assert complete['status'] == 'completed'
    assert complete['output']['dry_run'] is True
    assert 'publication' not in complete['output']
    assert 'submission' not in complete['output']
    assert clip.exists()
    assert not workflow.consume_once()


def test_kill_switch_and_cancel_prevent_execution(tmp_path, monkeypatch):
    workflow = engine(tmp_path)
    job = workflow.create(request())
    approve(workflow, job)
    monkeypatch.setenv('KILL_SWITCH', 'true')
    assert not workflow.consume_once()
    monkeypatch.delenv('KILL_SWITCH')
    workflow.set_kill_switch(True)
    assert not workflow.consume_once()
    workflow.cancel(job['id'])
    workflow.set_kill_switch(False)
    assert not workflow.consume_once()
    assert workflow.get(job['id'])['status'] == 'cancelled'


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_live_handoffs_require_review_public_post_and_external_submission_evidence(tmp_path, monkeypatch):
    workflow = engine(tmp_path)
    source = workflow.storage / 'uploads' / 'authorized.mp4'
    source.parent.mkdir()
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'testsrc2=size=320x180:rate=25', '-f', 'lavfi', '-i',
                    'sine=frequency=440', '-t', '6', '-c:v', 'libx264', '-preset',
                    'ultrafast', '-c:a', 'aac', str(source)], check=True)
    campaign = request()['campaign'] | {'pre_post_review': True}
    data = request(dry_run=False, source_url=None, source_path='uploads/authorized.mp4', campaign=campaign)
    monkeypatch.setitem(__import__('sys').modules, 'faster_whisper', None)
    job = workflow.create(data)
    approve(workflow, job)
    workflow.consume_once()
    job = workflow.get(job['id'])
    assert job['status'] == 'awaiting_transcript'
    workflow.provide_transcript(job['id'], '1\n00:00:00,000 --> 00:00:06,000\nA real software demonstration.\n')
    workflow.consume_once()
    job = workflow.get(job['id'])
    assert job['status'] == 'awaiting_clip_approval', job
    assert source.exists()
    with pytest.raises(ValueError, match='waiting'):
        workflow.record_publication(job['id'], 'https://www.youtube.com/shorts/demo', True, '2026-10-04T12:00:00Z')
    with pytest.raises(ValueError, match='brand draft'):
        approve(workflow, job)
    workflow.approve(job['id'], 'clip_review', job['approval_fingerprint'], True,
                     brand_draft_reference='Brand draft approval #123')
    workflow = engine(tmp_path)
    workflow.consume_once()
    assert workflow.get(job['id'])['status'] == 'awaiting_publication'
    with pytest.raises(ValueError, match='public'):
        workflow.record_publication(job['id'], 'https://www.youtube.com/shorts/demo', False, '2026-10-04T12:00:00Z')
    with pytest.raises(ValueError, match='platform'):
        workflow.record_publication(job['id'], 'https://www.instagram.com/reel/demo/', True, '2026-10-04T12:00:00Z')
    workflow.record_publication(job['id'], 'https://www.youtube.com/shorts/demo', True, '2026-10-04T12:00:00Z')
    job = workflow.get(job['id'])
    assert job['status'] == 'awaiting_submission'
    assert job['output']['submission_deadline'] == '2026-10-04T12:30:00+00:00'
    assert 'submission' not in job['output']
    with pytest.raises(ValueError, match='confirmation'):
        workflow.record_submission(job['id'], '', '2026-10-04T12:10:00Z')
    workflow.record_submission(job['id'], 'CR submission #456', '2026-10-04T12:10:00Z')
    job = workflow.get(job['id'])
    assert job['status'] == 'completed'
    assert job['output']['submission']['status'] == 'operator_confirmed'
    assert job['output']['submission']['within_deadline'] is True
    assert 'paid' not in job['output']
    assert source.exists()
    with pytest.raises(ValueError, match='waiting'):
        workflow.record_submission(job['id'], 'duplicate', '2026-10-04T12:10:00Z')


def test_abandoned_claim_is_recovered_without_changing_approval(tmp_path):
    workflow = engine(tmp_path)
    job = workflow.create(request())
    approve(workflow, job)
    with workflow.connection() as db:
        db.execute("UPDATE clipping_job SET status='running', updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (job['id'],))
    workflow.recover_interrupted()
    job = workflow.get(job['id'])
    assert job['status'] == 'queued'
    assert job['output']['approvals']['campaign_review']['approved'] is True


def test_storage_escape_and_nonfinite_timestamps_are_rejected(tmp_path):
    workflow = engine(tmp_path)
    with pytest.raises(ValueError, match='storage'):
        workflow.create(request(source_path='../outside.mp4'))
    with pytest.raises(ValueError):
        workflow.create(request(clip_plan={'duration_seconds': float('nan')}))


def test_environment_dry_run_overrides_live_request(tmp_path, monkeypatch):
    monkeypatch.setenv('DRY_RUN', 'true')
    job = engine(tmp_path).create(request(dry_run=False))
    assert job['payload']['dry_run'] is True


def test_cancel_during_ingestion_preserves_cancellation(tmp_path, monkeypatch):
    from clipping import media
    workflow = engine(tmp_path)
    job = workflow.create(request())
    approve(workflow, job)

    def cancelled_ingestion(*args):
        workflow.cancel(job['id'])
        return {'source_path': 'not-used.mp4'}

    monkeypatch.setattr(media, 'ingest', cancelled_ingestion)
    workflow.consume_once()
    assert workflow.get(job['id'])['status'] == 'cancelled'


@pytest.mark.parametrize('change', [
    {'campaign': []}, {'clip_plan': []}, {'source_url': 42},
    {'source_path': 42}, {'transcript_srt': []}, {'language': []},
    {'campaign': request()['campaign'] | {'pre_post_review': 1}},
    {'campaign': request()['campaign'] | {'rate_per_1000': -1}},
])
def test_invalid_input_shapes_return_validation_errors(tmp_path, change):
    with pytest.raises(ValueError):
        engine(tmp_path).create(request(**change))


def test_omitted_campaign_duration_limits_can_be_null(tmp_path):
    campaign = request()['campaign'] | {'duration_min': None, 'duration_max': None}
    assert engine(tmp_path).create(request(campaign=campaign))['status'] == 'awaiting_campaign_approval'


def test_failed_stage_preserves_failure_and_can_resume(tmp_path, monkeypatch):
    from clipping import media
    workflow = engine(tmp_path)
    job = workflow.create(request())
    approve(workflow, job)
    def unavailable(*args):
        raise ValueError('Source service unavailable')
    monkeypatch.setattr(media, 'ingest', unavailable)
    workflow.consume_once()
    job = workflow.get(job['id'])
    assert job['status'] == 'failed'
    assert job['output']['failure']['code'] == 'VALIDATION_ERROR'
    assert job['error'] == 'Content or artifact validation failed.'
    assert 'publication' not in job['output']
    assert workflow.retry(job['id'])['status'] == 'queued'


def test_changed_clip_cannot_be_approved(tmp_path):
    from clipping.media import file_hash
    workflow = engine(tmp_path)
    job = workflow.create(request())
    workflow.approve(job['id'], 'campaign_review', job['input_hash'], True)
    workflow._save(job['id'], {}, 'running', 'render_and_quality_check', 'queued')
    job = workflow.get(job['id'])
    artifact = workflow.storage / 'prepared.mp4'
    artifact.write_bytes(b'original video')
    workflow._save(job['id'], {'clip_path': 'prepared.mp4', 'clip_sha256': file_hash(artifact)},
                   'awaiting_clip_approval', 'clip_review', job['status'])
    job = workflow.get(job['id'])
    artifact.write_bytes(b'changed video')
    with pytest.raises(ValueError, match='changed'):
        approve(workflow, job)
    assert workflow.get(job['id'])['status'] == 'awaiting_clip_approval'


def test_concurrent_reward_updates_preserve_both_receipts(tmp_path, monkeypatch):
    import threading
    workflow = engine(tmp_path)
    job = workflow.create(request())
    workflow.approve(job['id'], 'campaign_review', job['input_hash'], True)
    workflow._save(job['id'], {}, 'running', 'render_and_quality_check', 'queued')
    workflow._save(job['id'], {}, 'awaiting_publication', 'publication')
    workflow._save(job['id'], {}, 'awaiting_submission', 'submission', 'awaiting_publication')
    workflow._save(job['id'], {'submission': {'reference': 'real external confirmation'}},
                   'completed', 'submission_recorded', 'awaiting_submission')
    barrier = threading.Barrier(2)
    original_get = workflow.get
    thread_calls = threading.local()
    def overlapping_read(job_id):
        result = original_get(job_id)
        if not getattr(thread_calls, 'called', False):
            thread_calls.called = True
            barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(workflow, 'get', overlapping_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda receipt: workflow.record_reward(job['id'], 'approved', receipt),
                      ['platform receipt A', 'platform receipt B']))
    history = original_get(job['id'])['output']['reward_history']
    assert {entry['reference'] for entry in history} == {'platform receipt A', 'platform receipt B'}
    monkeypatch.setattr(workflow, 'get', original_get)
    with pytest.raises(ValueError, match='amount'):
        workflow.record_reward(job['id'], 'paid', 'payment receipt')
