import subprocess
import sys
from pathlib import Path

import pytest

from clipping import media
from clipping.workflow import ClippingWorkflow


def payload(preview=True):
    return {'campaign': {'title': 'Test', 'url': 'https://example.com/campaign',
        'platform': 'youtube', 'rules': 'Test only', 'rights_notes': 'Authorized test'},
        'source_url': 'https://www.youtube.com/watch?v=Uv1PyE8J38w',
        'preview_only': preview, 'dry_run': False,
        'clip_plan': {'start_seconds': 0, 'duration_seconds': 5, 'aspect_ratio': '9:16'}}


def test_download_uses_parallel_fragments_resume_and_a_realistic_deadline(tmp_path, monkeypatch):
    called = []
    def disconnected(args, **kwargs):
        called.append((args, kwargs))
        raise ValueError('Connection reset')
    monkeypatch.setattr(media, 'command', disconnected)
    with pytest.raises(media.SourceUnavailable):
        media.ingest(payload(), {}, tmp_path, tmp_path)
    args, options = called[0]
    assert '--concurrent-fragments' in args, 'Downloads still use one fragment connection'
    assert args[args.index('--concurrent-fragments') + 1] == '4'
    assert '--continue' in args and '--part' in args
    assert 'height<=1080' in args[args.index('-f') + 1]
    assert options['timeout'] >= 900
    assert options['kill_tree']
    assert '--download-sections' in args
    assert args[args.index('--download-sections') + 1] == '*0-8'


def test_interrupted_checkpoint_reuses_complete_source_not_format_fragments(tmp_path, monkeypatch):
    (tmp_path / 'source.mp4').write_bytes(b'complete-source')
    (tmp_path / 'source.f137.mp4').write_bytes(b'video-only-format')
    def unexpected(*args, **kwargs):
        pytest.fail('A complete source was downloaded again')
    monkeypatch.setattr(media, 'command', unexpected)
    monkeypatch.setattr(media, 'probe', lambda path: {'format': {'duration': '30'},
        'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]})
    result = media.ingest(payload(), {}, tmp_path, tmp_path)
    assert result['source_path'] == 'source.mp4'
    assert (tmp_path / 'source.mp4').read_bytes() == b'complete-source'


def test_source_access_errors_are_distinct_and_do_not_expose_signed_urls(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise ValueError('HTTP Error 403: https://example.test/?token=SECRET_SENTINEL')
    monkeypatch.setattr(media, 'command', denied)
    with pytest.raises(media.SourceAccessRequired) as failure:
        media.ingest(payload(), {}, tmp_path, tmp_path)
    assert 'SECRET_SENTINEL' not in str(failure.value)


def test_download_captures_only_replay_bins_and_keeps_them_after_resume(tmp_path, monkeypatch):
    import json
    heatmap = [{'start_time': 0, 'end_time': 15, 'value': .1},
               {'start_time': 15, 'end_time': 30, 'value': 1}]
    calls = []
    def download(args, **kwargs):
        calls.append(args)
        (tmp_path / 'source.mp4').write_bytes(b'complete-source')
        (tmp_path / 'source-heatmap.json').write_text(json.dumps(heatmap) + '\n')
    monkeypatch.setattr(media, 'command', download)
    monkeypatch.setattr(media, 'probe', lambda path: {'format': {'duration': '30'},
        'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]})
    data = payload()
    data['clip_plan']['duration_seconds'] = 30
    result = media.ingest(data, {}, tmp_path, tmp_path)
    assert result['source_heatmap'] == heatmap
    assert 'after_move:%(heatmap)j' in calls[0]
    assert '--write-info-json' not in calls[0], 'Persist bins without signed media URLs'
    monkeypatch.setattr(media, 'command', lambda *args, **kwargs: pytest.fail('Downloaded again'))
    assert media.ingest(data, {}, tmp_path, tmp_path)['source_heatmap'] == heatmap


@pytest.mark.parametrize('preview', [False, True])
def test_transient_failure_stops_at_limit_and_preserves_approval_across_restarts(tmp_path, monkeypatch, preview):
    from clipping import workflow as module
    engine = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    job = engine.create(payload(preview))
    if not preview:
        engine.approve(job['id'], 'campaign_review', job['input_hash'], True)
    def unavailable(*args):
        raise media.SourceUnavailable('Temporary connection failure')
    monkeypatch.setattr(media, 'ingest', unavailable)
    monkeypatch.setattr(module, 'utcnow', lambda: '2026-10-10T10:00:00+00:00')
    for attempt in range(1, 3):
        assert engine.consume_once()
        job = engine.get(job['id'])
        assert job['status'] == 'retry_scheduled', 'Temporary failure terminated an authorized job'
        retry = job['output']['automation_retry']
        assert retry['failed_attempts'] == attempt
        assert retry['next_attempt_at'] > module.utcnow()
        assert retry['maximum_attempts'] == 3
        engine = ClippingWorkflow(engine.database, engine.storage)
        assert not engine.consume_once(), 'Restart bypassed the saved backoff'
        monkeypatch.setattr(module, 'utcnow', lambda due=retry['next_attempt_at']: due)
    assert engine.consume_once()
    job = engine.get(job['id'])
    assert job['status'] == 'failed'
    assert job['output']['automation_retry']['failed_attempts'] == 3
    assert job['output']['automation_retry']['next_attempt_at'] is None
    assert not engine.consume_once()
    if not preview:
        assert job['output']['approvals']['campaign_review']['approved']
    engine.cancel(job['id'])
    assert not engine.consume_once()


def test_pause_interrupts_a_running_source_and_keeps_job_recoverable(tmp_path, monkeypatch):
    engine = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    job = engine.create(payload())
    def paused_download(*args):
        engine.set_kill_switch(True)
        media.command([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=30)
    monkeypatch.setattr(media, 'ingest', paused_download)
    engine.consume_once()
    job = engine.get(job['id'])
    assert job['status'] == 'blocked'
    assert 'paused' in job['error'].lower()
    engine.set_kill_switch(False)
    assert engine.retry(job['id'])['status'] == 'queued'


def test_downloader_stop_signal_terminates_its_process(tmp_path):
    assert hasattr(media, 'ProcessingInterrupted'), 'Media operations cannot be interrupted'
    marker = tmp_path / 'should-not-exist'
    started = tmp_path / 'started'
    child = (f'from pathlib import Path; import time; Path({str(started)!r}).write_text("started"); '
             f'time.sleep(2); Path({str(marker)!r}).write_text("alive")')
    with pytest.raises(media.ProcessingInterrupted):
        media.command([sys.executable, '-c', child], should_stop=started.exists, timeout=10)
    assert started.exists(), 'Test must interrupt an actual running subprocess'
    assert not marker.exists()


def test_shutdown_preserves_a_running_job_for_restart(tmp_path, monkeypatch):
    engine = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    job = engine.create(payload())
    def restarting(*args):
        engine.shutdown_requested = True
        raise media.ProcessingInterrupted('Application shutdown')
    monkeypatch.setattr(media, 'ingest', restarting)
    assert engine.consume_once()
    assert engine.get(job['id'])['status'] == 'queued'
    assert not engine.consume_once()
    restarted = ClippingWorkflow(engine.database, engine.storage)
    assert restarted.get(job['id'])['status'] == 'queued'
