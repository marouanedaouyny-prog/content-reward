import json
import socket
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError

import httpx
import pytest


def tunnel_tools():
    from clipping import instagram_tunnel
    return instagram_tunnel


def test_tunnel_selection_uses_https_for_the_expected_local_app():
    mod = tunnel_tools()
    tunnels = {'tunnels': [
        {'public_url': 'https://other.ngrok-free.app', 'config': {'addr': 'http://localhost:3000'}},
        {'public_url': 'http://clip.ngrok-free.app', 'config': {'addr': 'http://localhost:8000'}},
        {'public_url': 'https://clip.ngrok-free.app', 'config': {'addr': 'http://127.0.0.1:8000'}},
    ]}
    assert mod.select_tunnel(tunnels) == 'https://clip.ngrok-free.app'


@pytest.mark.parametrize('url', [
    'http://clip.ngrok-free.app', 'https://user:password@clip.ngrok-free.app',
    'https://clip.ngrok-free.app/other', 'https://clip.ngrok-free.app?secret=value',
    'https://clip.ngrok-free.app#secret', 'https://clip.ngrok-free.app\nINJECTED=value',
])
def test_invalid_public_address_does_not_modify_configuration(tmp_path, url):
    mod = tunnel_tools()
    config = tmp_path / '.env.local'
    original = b'INSTAGRAM_APP_SECRET=private-fixture-secret\r\n'
    config.write_bytes(original)
    with pytest.raises(ValueError):
        mod.configure_redirect(config, url)
    assert config.read_bytes() == original


def test_redirect_update_preserves_credentials_and_newline_format(tmp_path):
    mod = tunnel_tools()
    config = tmp_path / '.env.local'
    original = (b'\xef\xbb\xbfINSTAGRAM_APP_ID=1234567890\r\n'
                b'INSTAGRAM_APP_SECRET="private-fixture-secret"\r\n'
                b'# Keep this comment\r\n'
                b'INSTAGRAM_REDIRECT_URI=http://127.0.0.1:8000/old\r\n'
                b'UNRELATED_SETTING=original-value\r\n')
    config.write_bytes(original)
    callback = mod.configure_redirect(config, 'https://clip.ngrok-free.app')
    assert callback == 'https://clip.ngrok-free.app/api/v1/clipping/accounts/instagram/callback'
    expected = original.replace(b'http://127.0.0.1:8000/old', callback.encode())
    assert config.read_bytes() == expected


def test_missing_callback_is_appended_and_duplicate_callback_settings_are_removed(tmp_path):
    mod = tunnel_tools()
    config = tmp_path / '.env.local'
    config.write_text('INSTAGRAM_APP_SECRET=private-fixture-secret', encoding='utf-8')
    callback = mod.configure_redirect(config, 'https://clip.ngrok-free.app/')
    assert config.read_text() == 'INSTAGRAM_APP_SECRET=private-fixture-secret\nINSTAGRAM_REDIRECT_URI=' + callback + '\n'
    config.write_text(config.read_text() + 'INSTAGRAM_REDIRECT_URI=https://stale.example/callback\n')
    mod.configure_redirect(config, 'https://clip.ngrok-free.app')
    assert config.read_text().count('INSTAGRAM_REDIRECT_URI=') == 1


def test_tunnel_failure_diagnostics_redact_provider_details():
    mod = tunnel_tools()
    secret = 'private-fixture-secret-1234567890'
    log = json.dumps({'err': 'proxy connection refused at 127.0.0.1:9; token=' + secret,
                      'msg': 'failed to reconnect session'})
    result = mod.classify_failure(log)
    assert result['reason'] == 'proxy_connection_refused'
    assert secret not in json.dumps(result) and 'token=' not in json.dumps(result)
    assert mod.classify_failure('Agent too old. ERR_NGROK_121')['reason'] == 'agent_too_old'


def test_connection_timeout_does_not_configure_a_guessed_callback(tmp_path):
    mod = tunnel_tools()
    config = tmp_path / '.env.local'
    config.write_text('INSTAGRAM_APP_SECRET=private-fixture-secret\n')
    with pytest.raises(mod.TunnelUnavailable) as error:
        mod.wait_for_tunnel(lambda: {'tunnels': []}, lambda: False, lambda: '', timeout=0)
    assert error.value.reason == 'connection_timeout'
    assert 'INSTAGRAM_REDIRECT_URI' not in config.read_text()


def test_wait_reports_agent_error_without_polling_forever():
    mod = tunnel_tools()
    with pytest.raises(mod.TunnelUnavailable) as error:
        mod.wait_for_tunnel(lambda: {'tunnels': []}, lambda: False,
                            lambda: 'failed auth ERR_NGROK_121 private-fixture-secret', timeout=2)
    assert error.value.reason == 'agent_too_old'
    assert 'private-fixture-secret' not in str(error.value)


def test_agent_upgrade_updates_only_a_workspace_copy(tmp_path, monkeypatch):
    mod = tunnel_tools()
    source = tmp_path / 'installed' / 'ngrok.exe'
    source.parent.mkdir()
    source.write_bytes(b'original-installed-agent')
    cache = tmp_path / 'workspace' / 'ngrok-runtime'
    commands = []

    def update(args, **kwargs):
        commands.append(args)
        assert args[0] != str(source)
        assert Path(args[0]).read_bytes() == b'original-installed-agent'
        Path(args[0]).write_bytes(b'updated-agent-fixture')
        return 'Agent updated.'

    monkeypatch.setattr(mod, 'agent_command', update)
    updated = mod.upgrade_agent(source, cache)
    assert source.read_bytes() == b'original-installed-agent'
    assert updated.read_bytes() == b'updated-agent-fixture'
    assert commands[0][1:] == ['update']


def test_failed_agent_update_restores_existing_copy_and_hides_error_details(tmp_path, monkeypatch):
    mod = tunnel_tools()
    source = tmp_path / 'ngrok.exe'
    source.write_bytes(b'installed-agent')
    cache = tmp_path / 'runtime'
    cache.mkdir()
    previous = cache / 'ngrok.exe'
    previous.write_bytes(b'previous-cached-agent')

    def update(args, **kwargs):
        previous.write_bytes(b'partial-download')
        raise ValueError('Update failed: private-fixture-secret')

    monkeypatch.setattr(mod, 'agent_command', update)
    with pytest.raises(mod.TunnelUnavailable) as error:
        mod.upgrade_agent(source, cache)
    assert error.value.reason == 'agent_update_failed'
    assert 'private-fixture-secret' not in str(error.value)
    assert source.read_bytes() == b'installed-agent'
    assert previous.read_bytes() == b'previous-cached-agent'


def test_setup_retries_with_the_updated_agent_after_version_rejection(tmp_path, monkeypatch):
    mod = tunnel_tools()
    attempted = []
    upgraded = tmp_path / '.workflow-tests/ngrok-runtime/ngrok.exe'

    def setup(account, config, executable, saved_config, port, no_browser):
        attempted.append(executable)
        if len(attempted) == 1:
            raise mod.TunnelUnavailable('agent_too_old', ['ERR_NGROK_121'])
        return 0

    monkeypatch.setattr(mod, 'run_setup', setup)
    monkeypatch.setattr(mod, 'upgrade_agent', lambda *args: upgraded)
    monkeypatch.setattr(mod, 'emit', lambda result: None)
    result = mod.setup_with_upgrade(None, tmp_path / '.env.local', 'old-agent.exe', 'ngrok.yml')
    assert result == 0
    assert attempted == ['old-agent.exe', upgraded]


def test_setup_retries_only_once_and_does_not_update_for_other_failures(tmp_path, monkeypatch):
    mod = tunnel_tools()
    attempts = []
    updates = []

    def setup(*args):
        attempts.append(args)
        raise mod.TunnelUnavailable(reason, ['ERR_NGROK_121'] if reason == 'agent_too_old' else [])

    def update(*args):
        updates.append(args)
        return tmp_path / 'updated.exe'

    monkeypatch.setattr(mod, 'run_setup', setup)
    monkeypatch.setattr(mod, 'upgrade_agent', update)
    monkeypatch.setattr(mod, 'emit', lambda result: None)
    for reason, expected_attempts, expected_updates in (
        ('agent_too_old', 2, 1), ('ngrok_credentials_rejected', 1, 0),
    ):
        attempts.clear()
        updates.clear()
        with pytest.raises(mod.TunnelUnavailable) as error:
            mod.setup_with_upgrade(None, tmp_path / '.env.local', 'old.exe', 'ngrok.yml')
        assert error.value.reason == reason
        assert len(attempts) == expected_attempts and len(updates) == expected_updates


def test_network_preflight_accepts_a_reachable_provider_error(monkeypatch):
    mod = tunnel_tools()

    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 404, 'Not found', {}, None)

    monkeypatch.setattr(mod, 'build_opener', lambda *args: Opener())
    mod.check_provider_network()


def test_network_preflight_reports_refused_proxy_without_provider_text(monkeypatch):
    mod = tunnel_tools()

    class Opener:
        def open(self, request, timeout):
            raise URLError(ConnectionRefusedError('127.0.0.1:9 private-fixture-secret'))

    monkeypatch.setattr(mod, 'build_opener', lambda *args: Opener())
    with pytest.raises(mod.TunnelUnavailable) as error:
        mod.check_provider_network()
    assert error.value.reason == 'proxy_connection_refused'
    assert 'private-fixture-secret' not in str(error.value)


@pytest.mark.parametrize(('cause', 'category'), [
    (socket.gaierror('private-fixture-secret'), 'dns_error'),
    (ssl.SSLCertVerificationError('private-fixture-secret'), 'tls_error'),
    (TimeoutError('private-fixture-secret'), 'timeout'),
    (ConnectionRefusedError('private-fixture-secret'), 'connection_refused'),
])
def test_provider_preflight_identifies_the_host_and_transport_failure(monkeypatch, cause, category):
    mod = tunnel_tools()

    class Opener:
        def open(self, request, timeout):
            if request.full_url == 'https://api.instagram.com/':
                raise HTTPError(request.full_url, 404, 'Not found', {}, None)
            raise URLError(cause)

    monkeypatch.setattr(mod, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(mod, 'getproxies', lambda: {})
    with pytest.raises(mod.TunnelUnavailable) as error:
        mod.check_provider_network()
    assert error.value.diagnostics == {
        'stage': 'instagram_preflight', 'host': 'graph.instagram.com', 'failure_type': category,
    }
    assert 'private-fixture-secret' not in json.dumps(error.value.diagnostics)


def test_provider_http_failure_is_reported_without_the_response_body(monkeypatch):
    mod = tunnel_tools()

    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 503, 'private-fixture-secret', {}, None)

    monkeypatch.setattr(mod, 'build_opener', lambda *args: Opener())
    with pytest.raises(mod.TunnelUnavailable) as error:
        mod.check_provider_network()
    assert error.value.diagnostics == {
        'stage': 'instagram_preflight', 'host': 'api.instagram.com',
        'failure_type': 'provider_http_error', 'http_status': 503,
    }
    assert 'private-fixture-secret' not in str(error.value)


def test_ngrok_transport_failure_is_not_reported_as_an_instagram_failure():
    mod = tunnel_tools()
    with pytest.raises(mod.TunnelUnavailable) as error:
        mod.wait_for_tunnel(lambda: {}, lambda: False,
                            lambda: 'dial tcp: i/o timeout private-fixture-secret', timeout=2)
    assert error.value.reason == 'ngrok_network_unavailable'
    assert error.value.diagnostics == {
        'stage': 'ngrok_startup', 'host': 'ngrok_cloud', 'failure_type': 'timeout',
    }
    assert 'Instagram' not in str(error.value) and 'private-fixture-secret' not in str(error.value)


def test_diagnosis_reports_paths_and_each_provider_without_starting_authentication(tmp_path, monkeypatch):
    mod = tunnel_tools()
    executable = tmp_path / 'ngrok.exe'
    executable.write_bytes(b'fixture-agent')
    config = tmp_path / 'ngrok.yml'
    config.write_text('private-fixture-secret')
    commands = []

    def agent(args, **kwargs):
        commands.append(args)
        if args[1] == 'version':
            return 'ngrok version 3.39.11\nprivate-fixture-secret'
        return 'Valid configuration file private-fixture-secret'

    class Opener:
        def open(self, request, timeout):
            if request.full_url == 'https://api.instagram.com/':
                raise HTTPError(request.full_url, 404, 'Not found', {}, None)
            raise URLError(TimeoutError('private-fixture-secret'))

    monkeypatch.setattr(mod, 'agent_command', agent)
    monkeypatch.setattr(mod, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(mod, 'getproxies', lambda: {})
    result = mod.diagnose_setup(executable, config)
    assert result['ngrok_path'] == str(executable.resolve()) and result['ngrok_version'] == '3.39.11'
    assert result['ngrok_config_valid'] is True and result['proxy_configured'] is False
    assert result['instagram_checks'][0]['status'] == 'reachable'
    assert result['instagram_checks'][1]['failure_type'] == 'timeout'
    assert result['instagram_checks'][1]['host'] == 'graph.instagram.com'
    assert 'private-fixture-secret' not in json.dumps(result)
    assert [call[1] for call in commands] == ['version', 'config']


@pytest.fixture
def auth_account(tmp_path, monkeypatch):
    from clipping.instagram import InstagramConnection
    from clipping.workflow import ClippingWorkflow
    for key in ('INSTAGRAM_APP_ID', 'INSTAGRAM_APP_SECRET', 'INSTAGRAM_REDIRECT_URI',
                'INSTAGRAM_ACCESS_TOKEN', 'INSTAGRAM_ACCOUNT_ID', 'INSTAGRAM_GRAPH_VERSION'):
        monkeypatch.delenv(key, raising=False)
    config = tmp_path / '.env.local'
    config.write_text('INSTAGRAM_APP_ID=1234567890\nINSTAGRAM_APP_SECRET=private-fixture-secret\n')
    tunnel_tools().configure_redirect(config, 'https://clip.ngrok-free.app')
    engine = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    return InstagramConnection(engine, config)


@pytest.mark.asyncio
async def test_separate_auth_service_persists_https_authorization_for_the_workspace(auth_account, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    import clipping.instagram as provider
    from clipping.instagram import InstagramConnection
    mod = tunnel_tools()
    exchanges = []
    token = 'long-token-private-fixture-1234567890'

    def exchange(request):
        exchanges.append(request)
        if request.get_method() == 'POST':
            return {'access_token': 'short-token-private-fixture-1234567890'}
        return {'access_token': token, 'expires_in': 5184000}

    def get(path, fields, credential):
        assert credential == token
        if path == 'me':
            return {'id': '17841400000000001', 'username': 'fixture.creator'}
        return {'data': [{'permission': 'instagram_business_basic', 'status': 'granted'},
                         {'permission': 'instagram_business_content_publish', 'status': 'granted'}]}

    monkeypatch.setattr(auth_account, '_json_request', exchange)
    monkeypatch.setattr(provider, 'instagram_get', get)
    app = mod.authentication_app(auth_account)
    base = '/api/v1/clipping/accounts/instagram'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://clip.ngrok-free.app') as client:
        page = await client.get('/')
        assert page.status_code == 200 and 'Connect Instagram' in page.text
        assert auth_account.oauth_redirect_uri() in page.text
        assert 'private-fixture-secret' not in page.text
        assert (await client.get('/api/v1/jobs')).status_code == 404
        started = await client.post(base + '/connect', json={})
        assert started.status_code == 200 and 'secure' in started.headers['set-cookie'].lower()
        state = parse_qs(urlparse(started.json()['authorization_url']).query)['state'][0]
        callback = await client.get(base + '/callback', params={'state': state, 'code': 'private-code-fixture'})
        assert callback.status_code == 303 and 'instagram=connected' in callback.headers['location']
        checked = (await client.get(base)).json()
        assert checked['status'] == 'verified' and checked['content_publish_permission'] is True
        assert not checked['publishing_enabled'] and token not in json.dumps(checked)
    expected = auth_account.oauth_redirect_uri()
    assert parse_qs(exchanges[0].data.decode())['redirect_uri'] == [expected]
    restored = InstagramConnection(auth_account.engine, auth_account.credential_file)
    assert restored.status()['status'] == 'verified'


@pytest.mark.asyncio
async def test_authentication_service_rejects_another_browser_origin(auth_account):
    mod = tunnel_tools()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mod.authentication_app(auth_account)),
                                 base_url='https://clip.ngrok-free.app') as client:
        result = await client.post('/api/v1/clipping/accounts/instagram/connect', json={},
                                   headers={'Origin': 'https://untrusted.example'})
        assert result.status_code == 403
