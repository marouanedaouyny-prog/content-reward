import json
from datetime import datetime, timezone

import pytest


def module():
    from clipping import orchestrator
    return orchestrator


def config():
    return module().Config(provider='public', caption_style='colorized', framing_mode='fit')


def connected_pipeline(monkeypatch):
    from clipping import media, trends
    mod = module()
    counts = {'search': 0, 'ingest': 0, 'transcribe': 0, 'render': 0}
    monkeypatch.setattr(mod, 'check_environment', lambda *args: None)
    monkeypatch.setattr(mod, 'check_browser', lambda *args: None)
    monkeypatch.setattr(mod, 'verify_export', lambda engine, job, folder: {
        'checks': {'full_decode': True}, 'frames': [], 'human_review_required': True})

    def discover(niche):
        counts['search'] += 1
        return [{'id': 'abcdefghijk', 'title': 'Why a business needs a strong team',
                 'uploader': 'Fixture creator', 'view_count': 500000, 'duration': 1800,
                 'timestamp': datetime.now(timezone.utc).timestamp() - 86400}]

    def ingest(data, output, folder, storage):
        counts['ingest'] += 1
        (folder / 'source.mp4').write_bytes(b'UNIT TEST SOURCE')
        return {'source_path': (folder / 'source.mp4').relative_to(storage).as_posix(),
                'source_duration': 1800, 'synthetic_source': False}

    def transcribe(data, output, folder, storage):
        counts['transcribe'] += 1
        path = folder / 'transcript.json'
        path.write_text(json.dumps({'segments': [
            {'start': 0, 'end': 10, 'text': 'Why does a business need a strong team?'},
            {'start': 10, 'end': 30, 'text': 'Three people working together can solve the problem.'}]}))
        return {'transcript_path': path.relative_to(storage).as_posix(),
                'transcript_origin': 'faster_whisper:en'}

    def render(data, output, folder, storage):
        counts['render'] += 1
        assert data['caption_style'] == 'colorized'
        assert data['framing_mode'] == 'fit'
        path = folder / 'clip.mp4'
        path.write_bytes(b'UNIT TEST EXPORT')
        (folder / 'subtitles.srt').write_text('1\n00:00:00,000 --> 00:00:30,000\nFixture only.\n')
        return {'clip_path': path.relative_to(storage).as_posix(), 'clip_sha256': media.file_hash(path),
                'subtitle_path': (folder / 'subtitles.srt').relative_to(storage).as_posix()}

    monkeypatch.setattr(trends, 'discover', discover)
    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(media, 'transcribe', transcribe)
    monkeypatch.setattr(media, 'render', render)
    return counts


def test_new_orders_search_fresh_and_produce_their_own_result(tmp_path, monkeypatch):
    counts = connected_pipeline(monkeypatch)
    mod = module()
    first = mod.Controller(tmp_path, config(), emit=lambda _: None)
    result = first.run(connection_attempts=1, retry_delay=0)
    assert result['status'] == 'ready_for_review'
    assert result['review']['human_review_required'] is True
    assert result['result']['selection_note'] and result['result']['post_caption']
    second = mod.Controller(tmp_path, config(), emit=lambda _: None)
    assert second.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert second.state['id'] != first.state['id']
    assert second.state['job_id'] != first.state['job_id']
    assert counts == {'search': 12, 'ingest': 2, 'transcribe': 2, 'render': 2}


def test_connection_failure_is_bounded_saved_and_resumed_without_a_fake_clip(tmp_path, monkeypatch):
    mod = module()
    counts = connected_pipeline(monkeypatch)
    attempts = []

    def unavailable(*args):
        attempts.append(1)
        raise mod.ConnectionIssue('youtube_connection_unavailable')

    monkeypatch.setattr(mod, 'check_browser', unavailable)
    events = []
    controller = mod.Controller(tmp_path, config(), emit=events.append, sleeper=lambda _: None)
    result = controller.run(connection_attempts=2, retry_delay=0)
    assert len(attempts) == 2
    assert result['status'] == 'connection_unavailable' and result.get('result') is None
    assert result['attempt'] == 2 and result['retry_in_seconds'] is None
    assert counts['search'] == 0 and result['resume_command']
    monkeypatch.setattr(mod, 'check_browser', lambda *args: None)
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert resumed.state['id'] == controller.state['id']
    assert resumed.run(connection_attempts=1)['status'] == 'ready_for_review'


def test_download_recovery_keeps_the_same_order_and_does_not_search_again(tmp_path, monkeypatch):
    from clipping import media
    mod = module()
    counts = connected_pipeline(monkeypatch)
    original = media.ingest
    monkeypatch.setattr(media, 'ingest', lambda *args: (_ for _ in ()).throw(
        media.SourceUnavailable('Temporary connection failure')))
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    assert controller.run(connection_attempts=1)['status'] == 'connection_unavailable'
    job_id = controller.state['job_id']
    monkeypatch.setattr(media, 'ingest', original)
    restored = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert restored.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert restored.state['job_id'] == job_id and counts['search'] == 6
    assert counts['transcribe'] == 1


def test_setup_errors_are_not_retried_and_unexpected_errors_are_redacted(tmp_path, monkeypatch):
    mod = module()
    connected_pipeline(monkeypatch)
    calls = []

    def missing(*args):
        calls.append(1)
        raise mod.SetupIssue('ffmpeg_missing')

    monkeypatch.setattr(mod, 'check_environment', missing)
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    assert controller.run(connection_attempts=3)['status'] == 'setup_required'
    assert len(calls) == 1
    monkeypatch.setattr(mod, 'check_environment', lambda *args: (_ for _ in ()).throw(
        ValueError('SECRET_SENTINEL https://example.test/?token=SECRET_SENTINEL')))
    events = []
    broken = mod.Controller(tmp_path, config(), emit=events.append)
    assert broken.run(connection_attempts=1)['status'] == 'failed'
    assert 'SECRET_SENTINEL' not in broken.manifest.read_text()
    assert 'SECRET_SENTINEL' not in json.dumps(events)


def test_resume_after_transcription_does_not_download_or_transcribe_again(tmp_path, monkeypatch):
    from clipping import media
    mod = module()
    counts = connected_pipeline(monkeypatch)
    original = media.render
    monkeypatch.setattr(media, 'render', lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    assert controller.run(connection_attempts=1)['status'] == 'interrupted'
    monkeypatch.setattr(media, 'render', original)
    restored = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert restored.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert counts['search'] == 6 and counts['ingest'] == counts['transcribe'] == 1


def test_finished_order_resume_does_not_run_a_new_search(tmp_path, monkeypatch):
    mod = module()
    counts = connected_pipeline(monkeypatch)
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    controller.run(connection_attempts=1)
    restored = mod.Controller(tmp_path, resume=controller.state['id'], emit=lambda _: None)
    assert restored.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert counts['search'] == 6 and counts['render'] == 1


def test_inaccessible_source_uses_the_next_fresh_candidate_without_researching(tmp_path, monkeypatch):
    from clipping import media, trends
    mod = module()
    counts = connected_pipeline(monkeypatch)
    original_search, original_ingest = trends.discover, media.ingest

    def two_sources(niche):
        record = original_search(niche)[0]
        return [record, {**record, 'id': 'lmnopqrstuv', 'view_count': 400000}]

    attempted = []

    def ingest(data, *args):
        attempted.append(data['source_url'])
        if 'abcdefghijk' in data['source_url']:
            raise media.SourceAccessRequired('Source access unavailable')
        return original_ingest(data, *args)

    monkeypatch.setattr(trends, 'discover', two_sources)
    monkeypatch.setattr(media, 'ingest', ingest)
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'ready_for_review'
    assert len(attempted) == 2 and counts['search'] == 6
    assert result['source_id'] == 'lmnopqrstuv'
    assert result['rejected_sources'] == ['abcdefghijk']


def test_failed_export_recheck_clears_the_previous_ready_result(tmp_path, monkeypatch):
    mod = module()
    connected_pipeline(monkeypatch)
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    controller.run(connection_attempts=1)
    result_file = controller.folder / 'result.json'
    assert result_file.is_file()
    monkeypatch.setattr(mod, 'verify_export', lambda *args: (_ for _ in ()).throw(ValueError('Changed clip')))
    restored = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    result = restored.run(connection_attempts=1)
    assert result['status'] == 'quality_failed'
    assert result.get('result') is None
    assert not result_file.exists()


def test_exclusive_resume_recovers_a_running_job_after_a_process_crash(tmp_path, monkeypatch):
    from clipping import media
    mod = module()
    counts = connected_pipeline(monkeypatch)
    original = media.render
    monkeypatch.setattr(media, 'render', lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    controller.run(connection_attempts=1)
    job = controller.engine.get(controller.state['job_id'])
    controller.engine._save(job['id'], job['output'], 'running', job['current_step'], expected='queued')
    monkeypatch.setattr(media, 'render', original)
    restored = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert restored.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert counts['ingest'] == counts['transcribe'] == 1


def test_exclusive_resume_finishes_only_unsearched_niches_after_a_crash(tmp_path, monkeypatch):
    from clipping import trends
    from clipping.workflow import ClippingWorkflow
    mod = module()
    counts = connected_pipeline(monkeypatch)
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    engine = ClippingWorkflow(controller.folder / 'workflow.db', tmp_path)
    research = trends.TrendResearchAgent(engine)
    scan = research.request_scan()
    first = trends.NICHES[0]
    scan['results'] = [trends.candidate(trends.discover(first)[0], first)]
    scan['searched_niches'] = [first['name']]
    research._save(scan, 'running')
    controller.update(research_run_id=scan['id'])
    restored = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert restored.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert counts['search'] == 6


def test_transcription_can_resume_after_the_operator_repairs_its_runtime(tmp_path, monkeypatch):
    from clipping import media
    mod = module()
    counts = connected_pipeline(monkeypatch)
    original = media.transcribe
    monkeypatch.setattr(media, 'transcribe', lambda *args: (_ for _ in ()).throw(
        media.TranscriptRequired('Automatic transcription unavailable')))
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    assert controller.run(connection_attempts=1)['status'] == 'transcript_required'
    monkeypatch.setattr(media, 'transcribe', original)
    restored = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert restored.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert counts['search'] == 6 and counts['ingest'] == counts['transcribe'] == 1


def test_order_lock_and_resume_paths_prevent_duplicate_or_outside_work(tmp_path):
    mod = module()
    controller = mod.Controller(tmp_path, config(), emit=lambda _: None)
    with mod.order_lock(controller.folder):
        restored = mod.Controller(tmp_path, resume=controller.state['id'], emit=lambda _: None)
        assert restored.run(connection_attempts=1)['status'] == 'already_running'
    with pytest.raises(ValueError, match='order'):
        mod.Controller(tmp_path, resume='../outside', emit=lambda _: None)


def test_browser_startup_classification_distinguishes_network_and_permission_errors():
    from clipping.youtube_browser import browser_failure_reason
    network = RuntimeError('No driver')
    network.__cause__ = RuntimeError('error sending request for URL https://example.test/?token=SECRET')
    assert browser_failure_reason(network) == 'browser_connection_unavailable'
    assert browser_failure_reason(PermissionError('Access is denied')) == 'browser_execution_refused'
    assert browser_failure_reason(RuntimeError('Browser version mismatch')) == 'driver_or_browser_unavailable'
    assert browser_failure_reason(RuntimeError('session not created')) == 'browser_session_not_created'


def test_public_preflight_fails_fast_on_a_connection_problem_without_leaking_provider_details(monkeypatch):
    from urllib.error import URLError
    mod = module()
    monkeypatch.setattr(mod, 'urlopen', lambda *args, **kwargs: (_ for _ in ()).throw(
        URLError('SECRET_SENTINEL proxy connection refused')))
    with pytest.raises(mod.ConnectionIssue) as failure:
        mod.check_browser(config())
    assert failure.value.code == 'youtube_connection_unavailable'
    assert 'SECRET_SENTINEL' not in str(failure.value)
