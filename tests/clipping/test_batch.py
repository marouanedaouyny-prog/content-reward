import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


def pipeline(tmp_path, monkeypatch):
    from clipping import media, orchestrator, sections, trends
    counts = {'search': 0, 'inspect': 0, 'download': 0, 'ingest': 0, 'transcribe': 0, 'render': 0, 'review': 0}
    monkeypatch.setenv('CLIPPING_DISCOVERY_PROVIDER', '')
    monkeypatch.setattr(orchestrator, 'check_environment', lambda *args: None)
    monkeypatch.setattr(orchestrator, 'check_browser', lambda *args: None)

    def discover(niche):
        counts['search'] += 1
        return [{'id': identifier, 'title': 'Building a successful business with a team',
                 'uploader': 'Fixture creator', 'view_count': 500000 - index * 10000, 'duration': 1800,
                 'timestamp': datetime.now(timezone.utc).timestamp() - 86400}
                for index, identifier in enumerate(('abcdefghijk', 'lmnopqrstuv'))]

    def inspect(source, folder, **kwargs):
        counts['inspect'] += 1
        segments = []
        topics = [
            ('Hire for a clear business role.', 'Write three skills before interviewing candidates.'),
            ('Cash flow keeps a business alive.', 'Keep reserves for taxes and supplier payments.'),
            ('Customers buy results.', 'Explain product benefits before listing features.'),
            ('Meetings should produce decisions.', 'Assign an owner and deadline to every action.'),
            ('Price reflects value.', 'Test a higher price with a small customer group.'),
            ('Reliable processes prevent mistakes.', 'Use a checklist before sending orders.'),
        ]
        for index, (opening, payoff) in enumerate(topics):
            start = 100 + index * 100
            segments += [{'start': start, 'end': start + 10, 'text': opening},
                         {'start': start + 10, 'end': start + 35, 'text': payoff}]
        return {'id': source['id'], 'title': source['title'], 'duration': 1800, 'segments': segments, 'heatmap': []}

    def download(source, plan, duration, folder, **kwargs):
        counts['download'] += 1
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'section.mp4'
        path.write_bytes(('PARTIAL FIXTURE ' + str(plan['start_seconds'])).encode())
        return {'path': path, 'source_offset': plan['start_seconds'] - 3, 'local_start': 3,
                'requested_end': plan['start_seconds'] + plan['duration_seconds'] + 3,
                'duration': plan['duration_seconds'] + 6, 'sha256': media.file_hash(path)}

    def ingest(data, output, folder, storage):
        counts['ingest'] += 1
        assert data.get('source_path') and not data.get('source_url')
        assert data['source_reference'], 'Every real batch needs independent timed source cues'
        path = storage / data['source_path']
        return {'source_path': data['source_path'], 'source_sha256': media.file_hash(path),
                'source_duration': 41, 'synthetic_source': False}

    def transcribe(data, output, folder, storage):
        counts['transcribe'] += 1
        path = folder / 'transcript.json'
        path.write_text(json.dumps({'segments': [{'start': 3, 'end': 38, 'text': 'A clear source thought.'}]}))
        return {'transcript_path': path.relative_to(storage).as_posix(), 'transcript_origin': 'faster_whisper:en'}

    def render(data, output, folder, storage):
        counts['render'] += 1
        assert data['clip_plan']['start_seconds'] == 3
        styles = config.caption_styles or [config.caption_style]
        expected = styles[(counts['render'] - 1) % len(styles)]
        assert data['caption_style'] == expected
        path, subs = folder / 'clip.mp4', folder / 'subtitles.srt'
        path.write_bytes(('TEST EXPORT ' + data['source_path']).encode())
        subs.write_text('1\n00:00:00,000 --> 00:00:35,000\nA clear source thought.\n')
        return {'clip_path': path.relative_to(storage).as_posix(), 'clip_sha256': media.file_hash(path),
                'subtitle_path': subs.relative_to(storage).as_posix()}

    def review(engine, job, folder):
        counts['review'] += 1
        assert job['output']['selected_clip_plan']['start_seconds'] == 3
        if media.file_hash(engine.artifact(job['id'], 'clip')) != job['output']['clip_sha256']:
            raise ValueError('Export changed')
        return {'checks': {'full_decode': True}, 'frames': [], 'human_review_required': True}

    for name, value in [('discover', discover)]:
        monkeypatch.setattr(trends, name, value)
    monkeypatch.setattr(sections, 'inspect_source', inspect)
    monkeypatch.setattr(sections, 'download_section', download)
    for name, value in [('ingest', ingest), ('transcribe', transcribe), ('render', render)]:
        monkeypatch.setattr(media, name, value)
    monkeypatch.setattr(orchestrator, 'verify_export', review)
    config = orchestrator.Config(provider='public', caption_style='studio', clip_count=4,
                                 partial_downloads=True, delivery_dir=str(tmp_path / 'delivered'))
    return orchestrator, config, counts


def test_fresh_batch_produces_four_unique_exports_from_one_source_in_one_folder(tmp_path, monkeypatch):
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'ready_for_review'
    clips = result['result']['clips']
    assert len(clips) == 4 and len({clip['job_id'] for clip in clips}) == 4
    assert {clip['source']['id'] for clip in clips} == {result['source_id']}
    assert all(clip['source_clip_plan']['start_seconds'] >= 100 for clip in clips)
    assert all(clip['post_caption'] for clip in clips)
    assert all(Path(clip['clip']).parent == tmp_path / 'delivered' for clip in clips)
    assert counts['search'] == len(mod.trends.NICHES) and counts['inspect'] == 1
    assert counts['download'] == counts['render'] == 4
    assert result['result']['full_video_downloaded'] is False


def test_batch_persists_render_attempt_outcomes_for_business_metrics(tmp_path, monkeypatch):
    from analytics.reports import business_metrics
    mod, config, _ = pipeline(tmp_path, monkeypatch)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review'
    report = business_metrics(controller.store)
    assert report['render_attempts'] == 4
    assert report['successful_render_rate'] == 1


def test_single_colorized_order_excludes_previous_source_and_resumes_without_more_downloads(tmp_path, monkeypatch):
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    config.clip_count = 1
    config.caption_style = 'colorized'
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    controller.update(excluded_source_ids=['abcdefghijk'])
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'ready_for_review'
    clips = result['result']['clips']
    assert len(clips) == 1
    assert clips[0]['source']['id'] == 'lmnopqrstuv'
    assert clips[0]['caption_style'] == 'colorized'
    assert result['result']['full_video_downloaded'] is False
    assert counts['download'] == counts['ingest'] == counts['render'] == 1
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert resumed.state['excluded_source_ids'] == ['abcdefghijk']
    assert resumed.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert counts['search'] == len(mod.trends.NICHES) and counts['download'] == counts['render'] == 1


def test_cli_single_clip_uses_partial_downloads(tmp_path, monkeypatch):
    from clipping import orchestrator
    captured = []

    class Controller:
        def __init__(self, storage, config, resume):
            config.validate()
            captured.append(config)

        def run(self, *args):
            return {'status': 'connection_unavailable'}

    monkeypatch.setattr(orchestrator, 'Controller', Controller)
    assert orchestrator.main(['--storage', str(tmp_path), '--clips', '1',
                              '--caption-style', 'colorized']) == 75
    assert captured[0].clip_count == 1 and captured[0].partial_downloads is True
    assert captured[0].caption_style == 'colorized'


def test_one_fresh_batch_assigns_and_preserves_a_different_style_for_each_clip(tmp_path, monkeypatch):
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    config.caption_styles = ['studio', 'pro', 'colorized', 'classic']
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'ready_for_review'
    assert [clip['caption_style'] for clip in result['result']['clips']] == config.caption_styles
    assert [controller.engine.get(clip['job_id'])['payload']['caption_style']
            for clip in result['result']['clips']] == config.caption_styles
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert resumed.config.caption_styles == config.caption_styles
    assert resumed.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert [clip['caption_style'] for clip in resumed.state['result']['clips']] == config.caption_styles
    assert counts['search'] == len(mod.trends.NICHES) and counts['download'] == counts['render'] == 4


def test_mixed_style_config_rejects_unknown_styles_and_non_sequences():
    import pytest

    from clipping.orchestrator import Config
    for styles in ('studio', [], ['studio', 'unknown'], ['studio'] * 5, [True]):
        config = Config(partial_downloads=True, clip_count=4)
        config.caption_styles = styles
        with pytest.raises((TypeError, ValueError)):
            config.validate()


def test_batch_resumes_after_connection_failure_without_redoing_finished_clips(tmp_path, monkeypatch):
    from clipping import media, sections
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    original = sections.download_section

    def fail_second(source, plan, duration, folder, **kwargs):
        if counts['download'] == 1:
            raise media.SourceUnavailable('Connection refused SECRET')
        return original(source, plan, duration, folder, **kwargs)

    monkeypatch.setattr(sections, 'download_section', fail_second)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'connection_unavailable'
    assert len(result['batch_results']) == 1 and counts['render'] == 1
    assert result.get('result') is None
    monkeypatch.setattr(sections, 'download_section', original)
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert resumed.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert counts['search'] == len(mod.trends.NICHES) and counts['inspect'] == 1
    assert counts['download'] == counts['render'] == 4


def test_missing_public_captions_tries_another_source_without_full_download(tmp_path, monkeypatch):
    from clipping import media, sections
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    original = sections.inspect_source
    rejected = []

    def inspect(source, folder, **kwargs):
        if not rejected:
            rejected.append(source['id'])
            raise media.SourceAccessRequired('No captions SECRET')
        return original(source, folder, **kwargs)

    monkeypatch.setattr(sections, 'inspect_source', inspect)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'ready_for_review'
    assert result['source_id'] not in rejected and result['rejected_sources'] == rejected
    assert counts['ingest'] == counts['download'] == 4
    assert 'SECRET' not in controller.manifest.read_text()


def test_completed_batch_rechecks_originals_before_presenting_ready_result(tmp_path, monkeypatch):
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'ready_for_review'
    clip = controller.engine.artifact(result['batch_results'][0]['job_id'], 'clip')
    Path(clip).write_bytes(b'TAMPERED')
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    result = resumed.run(connection_attempts=1)
    assert result['status'] == 'quality_failed' and result.get('result') is None
    assert not (resumed.folder / 'result.json').exists()
    assert not (tmp_path / 'delivered' / f'{result["id"][:8]}-result.json').exists()
    assert counts['search'] == len(mod.trends.NICHES) and counts['render'] == 4


def test_new_cli_defaults_to_four_partial_studio_clips_and_legacy_config_is_preserved(tmp_path, monkeypatch):
    from clipping import orchestrator
    captured = []

    class Controller:
        def __init__(self, storage, config, resume):
            captured.append(config)
        def run(self, *args):
            return {'status': 'connection_unavailable'}

    monkeypatch.setattr(orchestrator, 'Controller', Controller)
    assert orchestrator.main(['--storage', str(tmp_path)]) == 75
    assert captured[0].clip_count == 4 and captured[0].partial_downloads is True
    assert captured[0].caption_style == 'studio'
    saved_config = json.loads('{"provider": "public", "caption_style": "pro", "duration": 35}')
    legacy = orchestrator.Config(**saved_config)
    assert legacy.clip_count == 1 and legacy.partial_downloads is False


def test_module_entrypoint_preserves_typed_batch_setup_errors(tmp_path):
    script = '''
import runpy, sys
from clipping import orchestrator
orchestrator.check_environment = lambda *args: None
def blocked(*args):
    raise orchestrator.SetupIssue('browser_session_not_created')
orchestrator.check_browser = blocked
sys.argv = ['clipping.orchestrator', '--new', '--storage', sys.argv[1]]
runpy.run_module('clipping.orchestrator', run_name='__main__')
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True,
                            text=True, timeout=30, check=False)
    assert result.returncode == 2
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary['status'] == 'setup_required'
    assert summary['reason'] == 'browser_session_not_created'


def test_browser_startup_failure_falls_back_to_public_search_in_the_same_order(tmp_path, monkeypatch):
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    checks = []

    def connectivity(effective):
        checks.append(effective.provider)
        if effective.provider == 'selenium':
            raise mod.SetupIssue('browser_session_not_created')

    monkeypatch.setattr(mod, 'check_browser', connectivity)
    controller = mod.Controller(tmp_path, replace(config, provider='selenium'), emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'ready_for_review'
    assert checks == ['selenium', 'public']
    assert result['discovery_provider'] == 'public'
    assert result['fallback_reason'] == 'browser_session_not_created'
    assert result['config']['provider'] == 'selenium'
    assert result['config']['partial_downloads'] is True
    assert counts['search'] == len(mod.trends.NICHES) and counts['download'] == 4


def test_public_fallback_network_failure_is_saved_and_resume_does_not_restart_chrome(tmp_path, monkeypatch):
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    checks = []
    preflights = []
    monkeypatch.setattr(mod, 'check_environment', lambda effective, storage: preflights.append(effective.provider))

    def connectivity(effective):
        checks.append(effective.provider)
        if effective.provider == 'selenium':
            raise mod.SetupIssue('browser_session_not_created')
        raise mod.ConnectionIssue('youtube_connection_unavailable')

    monkeypatch.setattr(mod, 'check_browser', connectivity)
    controller = mod.Controller(tmp_path, replace(config, provider='selenium'), emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'connection_unavailable'
    assert result['discovery_provider'] == 'public' and counts['search'] == 0
    assert result.get('result') is None
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert resumed.run(connection_attempts=1)['status'] == 'connection_unavailable'
    assert checks == ['selenium', 'public', 'public']
    assert preflights == ['selenium', 'public']
    assert resumed.state['id'] == controller.state['id']
    assert 'SECRET' not in controller.manifest.read_text()


def test_browser_configuration_errors_are_reported_without_switching_providers(tmp_path, monkeypatch):
    mod, config, counts = pipeline(tmp_path, monkeypatch)
    checks = []

    def connectivity(effective):
        checks.append(effective.provider)
        raise mod.SetupIssue('proxy_configuration_unavailable')

    monkeypatch.setattr(mod, 'check_browser', connectivity)
    controller = mod.Controller(tmp_path, replace(config, provider='selenium'), emit=lambda _: None)
    result = controller.run(connection_attempts=1)
    assert result['status'] == 'setup_required'
    assert result['reason'] == 'proxy_configuration_unavailable'
    assert checks == ['selenium'] and not result.get('fallback_reason')
    assert counts['search'] == counts['download'] == 0
