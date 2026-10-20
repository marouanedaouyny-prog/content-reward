import importlib
import importlib.util
from datetime import datetime, timezone

import pytest

from clipping.workflow import ClippingWorkflow


def module():
    assert importlib.util.find_spec('clipping.trends'), 'Persistent trend research agent is missing'
    return importlib.import_module('clipping.trends')


def video(identifier='aaaaaaaaaaa', views=24000, hours=24):
    return {'id': identifier, 'title': 'A recorded gaming interview', 'uploader': 'Test creator',
        'view_count': views, 'timestamp': datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp() - hours * 3600,
        'duration': 1800, 'live_status': 'not_live'}


def agent(tmp_path, monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, 'now', lambda: datetime(2026, 10, 10, tzinfo=timezone.utc))
    engine = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    return mod.TrendResearchAgent(engine), mod


def test_live_research_is_persisted_deduplicated_and_explains_ranking(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    requested = research.request_scan()
    assert research.request_scan()['id'] == requested['id']
    calls = []
    def fetch(niche):
        calls.append(niche)
        return [video(), video(), video('bbbbbbbbbbb', 12000, 6)]
    monkeypatch.setattr(mod, 'discover', fetch)
    assert research.consume_once()
    saved = research.get(requested['id'])
    assert saved['status'] == 'completed'
    assert len(calls) == 6
    assert len(saved['results']) == 2
    first = saved['results'][0]
    assert first['id'] == 'bbbbbbbbbbb'
    assert first['views_per_hour_since_upload'] == 2000
    assert first['measured_growth_per_hour'] is None
    assert 'prediction' in saved['ranking_note'].lower()
    restored = mod.TrendResearchAgent(research.engine)
    assert restored.status()['latest']['id'] == saved['id']
    assert not restored.consume_once(), 'Completed research should wait for the scheduled scan'


def test_temporary_search_failure_retries_without_inventing_results(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    run = research.request_scan()
    def unavailable(niche):
        raise mod.DiscoveryUnavailable('Network connection unavailable')
    monkeypatch.setattr(mod, 'discover', unavailable)
    assert research.consume_once()
    failed = research.get(run['id'])
    assert failed['status'] == 'retry_scheduled'
    assert failed['results'] == []
    assert failed['next_attempt_at'] > '2026-10-10T00:00:00+00:00'
    assert not mod.TrendResearchAgent(research.engine).consume_once()


def test_search_pause_and_global_kill_prevent_requests(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    run = research.request_scan()
    monkeypatch.setattr(mod, 'discover', lambda niche: pytest.fail('Paused agent made a request'))
    research.set_enabled(False)
    assert not research.consume_once()
    assert research.get(run['id'])['status'] == 'queued'
    research.set_enabled(True)
    research.engine.set_kill_switch(True)
    assert not research.consume_once()


def test_ranker_rejects_live_old_invalid_sources_and_keeps_missing_metrics_unknown(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    research.request_scan()
    monkeypatch.setattr(mod, 'discover', lambda niche: [
        video('aaaaaaaaaaa') | {'live_status': 'is_live'}, video('bbbbbbbbbbb', hours=24*20),
        video('invalid-id'), video('ccccccccccc') | {'view_count': None, 'timestamp': None}])
    research.consume_once()
    result = research.status()['latest']['results']
    assert [item['id'] for item in result] == ['ccccccccccc']
    assert result[0]['views'] is None and result[0]['published_at'] is None
    assert result[0]['views_per_hour_since_upload'] is None
    with pytest.raises(ValueError, match='eligible'):
        research.preview(research.status()['latest']['id'])


def test_best_source_creates_a_private_preview_without_changing_campaigns(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    scan = research.request_scan()
    monkeypatch.setattr(mod, 'discover', lambda niche: [video()])
    research.consume_once()
    preview = research.preview(scan['id'])
    assert preview['payload']['source_url'] == 'https://www.youtube.com/watch?v=aaaaaaaaaaa'
    assert preview['payload']['preview_only'] is True
    assert preview['payload']['auto_clip'] is True
    assert preview['status'] == 'queued'
    assert research.preview(scan['id'])['id'] == preview['id']
    assert not preview['output'].get('publication')
    assert preview['payload']['source_selection']['checked_on'] == '2026-10-10'


def test_official_discovery_uses_recent_niche_search_then_video_statistics(monkeypatch):
    mod = module()
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-secret-never-returned')
    calls = []
    def api(resource, params):
        calls.append((resource, params))
        if resource == 'search':
            return {'items': [{'id': {'videoId': 'aaaaaaaaaaa'}}]}
        return {'items': [{'id': 'aaaaaaaaaaa', 'snippet': {'title': 'A clip',
            'channelTitle': 'Creator', 'publishedAt': '2026-10-09T00:00:00Z',
            'liveBroadcastContent': 'none'}, 'statistics': {'viewCount': '2000'},
            'contentDetails': {'duration': 'PT5M'}}]}
    monkeypatch.setattr(mod, 'youtube_api', api)
    entries = mod.discover(mod.NICHES[0])
    assert [call[0] for call in calls] == ['search', 'videos']
    assert calls[0][1]['type'] == 'video'
    assert calls[0][1]['videoDuration'] == 'long'
    assert 'publishedAfter' in calls[0][1] and 'chart' not in calls[0][1]
    assert entries[0]['duration'] == 300
    assert entries[0]['view_count'] == 2000
    assert 'test-secret-never-returned' not in str(entries)


def test_public_discovery_does_not_download_footage_or_use_unbounded_search(monkeypatch):
    mod = module()
    from clipping import media
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    calls = []
    def search(args, **options):
        calls.append((args, options))
        return '{"entries": []}'
    monkeypatch.setattr(media, 'command', search)
    assert mod.discover(mod.NICHES[0]) == []
    args, options = calls[0]
    assert '--skip-download' in args and '--flat-playlist' in args
    assert args[-1].startswith('ytsearch8:')
    extractor = pytest.importorskip('yt_dlp.extractor.youtube').YoutubeSearchIE
    assert extractor.suitable(args[-1]), 'The installed downloader must accept the actual search command'
    assert options['timeout'] <= 30


def test_public_search_checks_all_bounded_long_video_candidates_when_dates_are_missing(monkeypatch):
    import json
    mod = module()
    from clipping import media
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    calls = []
    def search(args, **options):
        calls.append(args)
        if args[-1].startswith('ytsearch8:'):
            return json.dumps({'entries': [video('aaaaaaaaaaa') | {'timestamp': None},
                video('bbbbbbbbbbb') | {'timestamp': None}, video('ccccccccccc') | {'timestamp': None}]})
        identifier = args[-1].split('=')[-1]
        return json.dumps(video(identifier))
    monkeypatch.setattr(media, 'command', search)
    entries = mod.discover(mod.NICHES[0])
    assert len(calls) == 4, 'Every bounded long-video candidate needs real publication data'
    assert entries[0]['timestamp'] is not None
    assert entries[1]['timestamp'] is not None
    assert entries[2]['timestamp'] is not None
    assert all('--skip-download' in args for args in calls)


def test_invalid_scraper_command_fails_without_endless_connection_retries(tmp_path, monkeypatch):
    from clipping import media
    research, mod = agent(tmp_path, monkeypatch)
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    scan = research.request_scan(auto_preview=True)
    def invalid(args, **options):
        raise ValueError('ERROR: Unsupported URL. private-test-value must not appear in reports')
    monkeypatch.setattr(media, 'command', invalid)
    research.consume_once()
    saved = research.get(scan['id'])
    assert saved['status'] == 'failed'
    assert saved['next_attempt_at'] is None
    assert saved['results'] == [] and research.engine.list() == []
    assert 'private-test-value' not in str(saved)
    assert all('command' in item['message'].lower() for item in saved['failures'])


def test_real_proxy_refusal_remains_a_retryable_source_failure(tmp_path, monkeypatch):
    from clipping import media
    research, mod = agent(tmp_path, monkeypatch)
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    scan = research.request_scan(auto_preview=True)
    def unavailable(args, **options):
        raise ValueError('Unable to connect to proxy: [WinError 10061] private-test-value')
    monkeypatch.setattr(media, 'command', unavailable)
    research.consume_once()
    saved = research.get(scan['id'])
    assert saved['status'] == 'retry_scheduled'
    assert saved['next_attempt_at']
    assert saved['results'] == [] and research.engine.list() == []
    assert 'private-test-value' not in str(saved)


def test_short_sources_cannot_be_selected_as_long_video_previews(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    run = research.request_scan()
    monkeypatch.setattr(mod, 'discover', lambda niche: [video() | {'duration': 300}])
    research.consume_once()
    assert not research.get(run['id'])['results'][0]['eligible_preview']
    with pytest.raises(ValueError, match='eligible'):
        research.preview(run['id'])


def test_search_to_clip_creates_exactly_one_ranked_job_and_survives_restart(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    run = research.request_scan(auto_preview=True)
    monkeypatch.setattr(mod, 'discover', lambda niche: [video(), video('bbbbbbbbbbb', 120000)])
    research.consume_once()
    saved = research.get(run['id'])
    job = research.engine.get(saved['preview_job_id'])
    assert job['payload']['source_url'].endswith('bbbbbbbbbbb')
    assert job['payload']['dry_run'] is False
    assert not job['payload'].get('transcript_srt')
    assert job['payload']['auto_clip'] and job['payload']['preview_only']
    restored = mod.TrendResearchAgent(research.engine)
    assert not restored.consume_once()
    assert len(research.engine.list()) == 1


def test_search_to_clip_does_not_make_a_fake_clip_when_search_fails(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    run = research.request_scan(auto_preview=True)
    monkeypatch.setattr(mod, 'discover', lambda niche: [])
    research.consume_once()
    saved = research.get(run['id'])
    assert saved.get('preview_error') and not saved.get('preview_job_id')
    assert research.engine.list() == []


def test_clip_requested_during_search_is_not_lost_by_the_search_worker(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    run = research.request_scan()
    requested = False
    def discover(niche):
        nonlocal requested
        if not requested:
            requested = True
            assert research.request_scan(auto_preview=True)['id'] == run['id']
        return [video()]
    monkeypatch.setattr(mod, 'discover', discover)
    research.consume_once()
    assert research.get(run['id'])['preview_job_id']
    assert len(research.engine.list()) == 1


def test_old_connection_retry_is_replaced_with_a_fresh_source_search(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    old = research.request_scan()
    research._save(old, 'retry_scheduled', '2026-10-13T12:00:00+00:00')
    monkeypatch.setattr(mod, 'now', lambda: datetime(2026, 10, 13, tzinfo=timezone.utc))
    new = research.request_scan(auto_preview=True)
    assert new['id'] != old['id']
    assert new['searched_niches'] == []
    assert new['auto_preview']


def test_search_clip_handoff_recovers_after_a_crash_without_duplicate_clips(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    scan = research.request_scan(auto_preview=True)
    scan['results'] = [mod.candidate(video(), mod.NICHES[0])]
    research._save(scan, 'completed')
    restored = mod.TrendResearchAgent(research.engine)
    assert restored.consume_once()
    job_id = restored.get(scan['id'])['preview_job_id']
    assert not restored.consume_once()
    assert restored.get(scan['id'])['preview_job_id'] == job_id
    assert len(research.engine.list()) == 1


def test_second_observation_measures_growth_and_keeps_the_original_snapshot(tmp_path, monkeypatch):
    research, mod = agent(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, 'discover', lambda niche: [video()])
    first = research.request_scan()
    research.consume_once()
    monkeypatch.setattr(mod, 'now', lambda: datetime(2026, 10, 10, 6, tzinfo=timezone.utc))
    monkeypatch.setattr(mod, 'discover', lambda niche: [video(views=30000)])
    second = research.request_scan()
    research.consume_once()
    assert research.get(second['id'])['results'][0]['measured_growth_per_hour'] == 1000
    assert research.get(first['id'])['results'][0]['views'] == 24000


@pytest.mark.asyncio
async def test_trend_api_queues_without_blocking_and_rejects_untrusted_origin(tmp_path, monkeypatch):
    mod = module()
    import httpx
    from clipping.app import app
    monkeypatch.setenv('CLIPPING_DATABASE', str(tmp_path / 'jobs.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(tmp_path / 'storage'))
    monkeypatch.setattr(mod.TrendResearchAgent, 'consume_once', lambda self: False)
    monkeypatch.setattr(ClippingWorkflow, 'consume_once', lambda self: False)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        queued = await client.post('/api/v1/clipping/trends/runs', json={})
        assert queued.status_code == 202
        assert queued.json()['status'] == 'queued'
        state = await client.get('/api/v1/clipping/trends')
        assert state.status_code == 200 and state.json()['latest']['id'] == queued.json()['id']
        assert (await client.post('/api/v1/clipping/trends/runs', json={},
            headers={'Origin': 'https://untrusted.example'})).status_code == 403
        assert (await client.get('/trends.js')).status_code == 200


@pytest.mark.asyncio
async def test_startup_runs_the_research_agent_independently_of_the_media_worker(tmp_path, monkeypatch):
    import asyncio
    import threading
    mod = module()
    from clipping.app import app
    monkeypatch.setenv('CLIPPING_DATABASE', str(tmp_path / 'jobs.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(tmp_path / 'storage'))
    monkeypatch.setenv('CLIPPING_TREND_AGENT', 'true')
    searched = threading.Event()
    monkeypatch.setattr(ClippingWorkflow, 'consume_once', lambda self: False)
    def discover(niche):
        searched.set()
        return []
    monkeypatch.setattr(mod, 'discover', discover)
    async with app.router.lifespan_context(app):
        assert await asyncio.to_thread(searched.wait, 2), 'Research worker did not start'
        state = app.state.trend_agent.status()
        assert state['latest']['status'] in ('running', 'completed')
