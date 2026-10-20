import importlib
import json
from datetime import datetime, timezone

import pytest

from clipping import media, trends


def browser_module():
    return importlib.import_module('clipping.youtube_browser')


def renderer(identifier, length='30:00'):
    return {'videoId': identifier, 'lengthText': {'simpleText': length}}


def test_browser_search_bounds_deduplicates_and_skips_known_short_videos():
    records = [renderer('aaaaaaaaaaa', '3:30'), renderer('bbbbbbbbbbb'),
               renderer('bbbbbbbbbbb'), renderer('ccccccccccc', '1:10:00')]
    records += [renderer(str(i).zfill(11)) for i in range(20)]
    tree = {'contents': [{'videoRenderer': item} for item in records]}
    result = browser_module().search_ids(tree)
    assert len(result) == 8
    assert result[:2] == ['bbbbbbbbbbb', 'ccccccccccc']
    assert len(result) == len(set(result))


def test_watch_metadata_uses_actual_exact_metrics_and_omits_stream_urls():
    player = {'videoDetails': {'videoId': 'aaaaaaaaaaa', 'title': 'A real interview',
        'author': 'Creator', 'viewCount': '235061', 'lengthSeconds': '1800'},
        'microformat': {'playerMicroformatRenderer': {'publishDate': '2026-10-13T10:00:00Z'}},
        'streamingData': {'formats': [{'url': 'private-signed-test-value'}]}}
    result = browser_module().watch_record(player, 'aaaaaaaaaaa')
    assert result['view_count'] == 235061 and result['duration'] == 1800
    assert result['published_at'] == '2026-10-13T10:00:00+00:00'
    assert 'private-signed-test-value' not in json.dumps(result)
    assert browser_module().watch_record(player, 'bbbbbbbbbbb') is None


def test_unknown_browser_metrics_are_not_invented_and_date_only_is_retained():
    player = {'videoDetails': {'videoId': 'aaaaaaaaaaa', 'viewCount': '1.2M views'},
              'microformat': {'playerMicroformatRenderer': {'publishDate': '2026-10-13'}}}
    result = browser_module().watch_record(player, 'aaaaaaaaaaa')
    assert result['view_count'] is None and result['duration'] is None
    assert result['upload_date'] == '20261013'
    assert not result.get('published_at')


def test_browser_preserves_the_inherited_proxy_without_exposing_credentials():
    mod = browser_module()
    assert mod.proxy_capabilities({'http': 'http://127.0.0.1:9', 'https': 'http://127.0.0.1:9'}) == {
        'proxyType': 'manual', 'httpProxy': '127.0.0.1:9', 'sslProxy': '127.0.0.1:9'}
    assert mod.proxy_capabilities({}) is None
    with pytest.raises(ValueError, match='proxy configuration'):
        mod.proxy_capabilities({'https': 'http://user:private-test-value@proxy.test:1234'})


def test_selenium_search_uses_the_configured_python_and_existing_pipeline(tmp_path, monkeypatch):
    from clipping.workflow import ClippingWorkflow
    monkeypatch.setenv('CLIPPING_SELENIUM_PYTHON', 'C:/Python314/python.exe')
    monkeypatch.setenv('CLIPPING_DISCOVERY_PROVIDER', 'selenium')
    monkeypatch.setenv('YOUTUBE_API_KEY', 'unused-private-test-value')
    monkeypatch.setattr(trends, 'youtube_api', lambda *args, **options: pytest.fail('Selenium mode used the API'))
    monkeypatch.setattr(trends, 'now', lambda: datetime(2026, 10, 14, tzinfo=timezone.utc))
    calls = []
    def discover(args, **options):
        calls.append((args, options))
        return json.dumps({'status': 'ok', 'entries': [{'id': 'aaaaaaaaaaa',
            'title': 'A long interview', 'uploader': 'Creator', 'view_count': 235061,
            'duration': 1800, 'published_at': '2026-10-13T10:00:00+00:00', 'live_status': 'not_live'}]})
    monkeypatch.setattr(media, 'command', discover)
    agent = trends.TrendResearchAgent(ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage'))
    run = agent.request_scan(auto_preview=True)
    agent.consume_once()
    saved = agent.get(run['id'])
    assert saved['provider'] == 'selenium_browser'
    job = agent.engine.get(saved['preview_job_id'])
    assert job['payload']['auto_clip'] and job['payload']['preview_only']
    assert not job['payload']['dry_run'] and not job['payload'].get('transcript_srt')
    assert job['payload']['source_url'] == 'https://www.youtube.com/watch?v=aaaaaaaaaaa'
    assert len(agent.engine.list()) == 1
    assert calls[0][0][0] == 'C:/Python314/python.exe'
    assert calls[0][1]['kill_tree'] and calls[0][1]['timeout'] <= 180
    assert 'unused-private-test-value' not in str(calls)


@pytest.mark.parametrize('status,expected', [('setup_blocked', ValueError),
                                          ('source_unavailable', trends.DiscoveryUnavailable)])
def test_browser_failures_are_classified_without_leaking_messages(monkeypatch, status, expected):
    monkeypatch.setenv('CLIPPING_DISCOVERY_PROVIDER', 'selenium')
    monkeypatch.setenv('CLIPPING_SELENIUM_PYTHON', 'C:/Python314/python.exe')
    monkeypatch.setattr(media, 'command', lambda *args, **options: json.dumps({
        'status': status, 'reason': 'driver_unavailable', 'message': 'private-test-value'}))
    with pytest.raises(expected) as failure:
        trends.discover(trends.NICHES[0])
    assert 'private-test-value' not in str(failure.value)


def test_switching_to_selenium_replaces_an_old_provider_scan(tmp_path, monkeypatch):
    from clipping.workflow import ClippingWorkflow
    monkeypatch.delenv('CLIPPING_DISCOVERY_PROVIDER', raising=False)
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    agent = trends.TrendResearchAgent(ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage'))
    old = agent.request_scan(auto_preview=True)
    monkeypatch.setenv('CLIPPING_DISCOVERY_PROVIDER', 'selenium')
    new = agent.request_scan(auto_preview=True)
    assert new['id'] != old['id'] and new['provider'] == 'selenium_browser'
    assert agent.get(old['id'])['status'] == 'expired'
    assert agent.request_scan(auto_preview=True)['id'] == new['id']


def test_browser_setup_error_is_redacted_and_does_not_claim_youtube_access(monkeypatch, capsys):
    from contextlib import contextmanager
    mod = browser_module()
    @contextmanager
    def unavailable():
        raise mod.BrowserSetupError('driver_or_browser_unavailable')
        yield
    monkeypatch.setattr(mod, 'browser_session', unavailable)
    assert mod.main(['--check']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {'status': 'setup_blocked', 'reason': 'driver_or_browser_unavailable'}
    assert not result.get('youtube_reachable')


def test_dom_fallback_keeps_only_canonical_youtube_video_identifiers():
    result = browser_module().dom_ids(['https://www.youtube.com/watch?v=aaaaaaaaaaa',
        'https://youtube.com/watch?v=aaaaaaaaaaa', 'https://evil.test/watch?v=bbbbbbbbbbb',
        'https://www.youtube.com/watch?v=ccccccccccc&v=ddddddddddd',
        'https://www.youtube.com/watch?v=eeeeeeeeeee&t=30'])
    assert result == ['aaaaaaaaaaa', 'eeeeeeeeeee']


def test_one_unavailable_watch_page_does_not_discard_other_browser_results():
    selenium_exceptions = pytest.importorskip('selenium.common.exceptions')
    class Browser:
        identifier = None
        def get(self, url):
            from urllib.parse import urlparse, parse_qs
            self.identifier = parse_qs(urlparse(url).query).get('v', [None])[0]
            if self.identifier == 'aaaaaaaaaaa':
                raise selenium_exceptions.WebDriverException('private-test-value')
        def execute_script(self, script):
            if 'ytInitialData' in script:
                return {'contents': [{'videoRenderer': renderer('aaaaaaaaaaa')},
                                     {'videoRenderer': renderer('bbbbbbbbbbb')}]}
            return {'videoDetails': {'videoId': self.identifier, 'viewCount': '235061',
                                    'lengthSeconds': '1800'}}
    records = browser_module().search(Browser(), 'full interview')
    assert [record['id'] for record in records] == ['bbbbbbbbbbb']
    assert 'private-test-value' not in str(records)
