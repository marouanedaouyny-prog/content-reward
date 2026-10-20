import importlib
import importlib.util
import json
from urllib.error import URLError

import pytest

from clipping.workflow import ClippingWorkflow

TOKEN = 'IGAA-test-token-fixture-1234567890'
ACCOUNT = '17841400000000001'


def module():
    assert importlib.util.find_spec('clipping.instagram'), 'Read-only Instagram connection is missing'
    return importlib.import_module('clipping.instagram')


def connection(tmp_path, monkeypatch):
    mod = module()
    config = tmp_path / '.env.local'
    config.write_text(f'INSTAGRAM_ACCESS_TOKEN={TOKEN}\nINSTAGRAM_ACCOUNT_ID={ACCOUNT}\n', encoding='utf-8')
    monkeypatch.delenv('INSTAGRAM_ACCESS_TOKEN', raising=False)
    monkeypatch.delenv('INSTAGRAM_ACCOUNT_ID', raising=False)
    monkeypatch.delenv('INSTAGRAM_GRAPH_VERSION', raising=False)
    engine = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    return mod.InstagramConnection(engine, config), mod, config


def verified_response(path, fields, token):
    if path == 'me':
        return {'id': ACCOUNT, 'username': 'test.creator'}
    return {'data': [{'permission': 'instagram_business_basic', 'status': 'granted'},
                     {'permission': 'instagram_business_content_publish', 'status': 'granted'}]}


def test_status_never_exposes_credentials_or_makes_external_requests(tmp_path, monkeypatch):
    account, mod, config = connection(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, 'instagram_get', lambda *args: pytest.fail('Status made a network request'))
    status = account.status()
    assert status['configured'] and status['account_id'] == ACCOUNT
    assert status['status'] == 'unverified' and status['publishing_enabled'] is False
    assert TOKEN not in json.dumps(status)
    assert 'access_token' not in status


def test_identity_and_permission_checks_are_persisted_but_do_not_enable_posting(tmp_path, monkeypatch):
    account, mod, config = connection(tmp_path, monkeypatch)
    calls = []
    def request(path, fields, token):
        calls.append(path)
        assert token == TOKEN
        return verified_response(path, fields, token)
    monkeypatch.setattr(mod, 'instagram_get', request)
    result = account.verify()
    assert result['status'] == 'verified'
    assert result['username'] == 'test.creator' and result['account_id'] == ACCOUNT
    assert result['content_publish_permission'] is True
    assert result['publishing_enabled'] is False
    assert calls == ['me', 'me/permissions']
    restored = mod.InstagramConnection(account.engine, config)
    assert restored.status()['username'] == 'test.creator'
    with account.engine.connection() as db:
        stored = str([tuple(row) for row in db.execute('SELECT * FROM clipping_setting')])
    assert TOKEN not in stored


def test_configured_account_must_match_the_token_identity(tmp_path, monkeypatch):
    account, mod, config = connection(tmp_path, monkeypatch)
    calls = []
    def request(path, *args):
        calls.append(path)
        return {'id': '17841499999999999', 'username': 'another.creator'}
    monkeypatch.setattr(mod, 'instagram_get', request)
    result = account.verify()
    assert result['status'] == 'account_mismatch'
    assert result['account_id'] == ACCOUNT
    assert result['returned_account_id'] == '17841499999999999'
    assert result['publishing_enabled'] is False
    assert calls == ['me']


def test_permission_failure_is_unknown_rather_than_a_false_publishing_claim(tmp_path, monkeypatch):
    account, mod, config = connection(tmp_path, monkeypatch)
    def request(path, *args):
        if path == 'me':
            return verified_response(path, '', TOKEN)
        raise mod.InstagramAPIError('permissions_unavailable')
    monkeypatch.setattr(mod, 'instagram_get', request)
    result = account.verify()
    assert result['status'] == 'profile_verified'
    assert result['content_publish_permission'] is None
    assert not result['permissions_checked']


def test_credential_replacement_invalidates_cached_success(tmp_path, monkeypatch):
    account, mod, config = connection(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, 'instagram_get', verified_response)
    assert account.verify()['status'] == 'verified'
    config.write_text(f'INSTAGRAM_ACCESS_TOKEN=new-token-fixture-1234567890\nINSTAGRAM_ACCOUNT_ID={ACCOUNT}\n', encoding='utf-8')
    status = account.status()
    assert status['status'] == 'unverified'
    assert status['username'] is None
    assert status['content_publish_permission'] is None


@pytest.mark.parametrize('change', ['replace', 'remove', 'api_version'])
def test_in_flight_check_cannot_verify_changed_configuration(tmp_path, monkeypatch, change):
    account, mod, config = connection(tmp_path, monkeypatch)

    def request(path, fields, token):
        if path == 'me/permissions':
            if change == 'api_version':
                monkeypatch.setenv('INSTAGRAM_GRAPH_VERSION', 'v99.0')
            else:
                config.write_text('' if change == 'remove' else
                    f'INSTAGRAM_ACCESS_TOKEN=new-token-fixture-1234567890\nINSTAGRAM_ACCOUNT_ID={ACCOUNT}\n',
                    encoding='utf-8')
        return verified_response(path, fields, token)

    monkeypatch.setattr(mod, 'instagram_get', request)
    result = account.verify()
    assert result['status'] == ('not_configured' if change == 'remove' else 'unverified')
    assert result['username'] is None and result['content_publish_permission'] is None
    assert result['last_checked_at'] is None
    assert account.status() == result
    with account.engine.connection() as db:
        assert db.execute("SELECT value FROM clipping_setting WHERE key='instagram_verification'").fetchone() is None


def test_fixed_https_host_bearer_header_and_bounded_request(monkeypatch):
    mod = module()
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, size): return b'{"id":"17841400000000001","username":"creator"}'
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            return Response()
    monkeypatch.setattr(mod, 'build_opener', lambda *handlers: Opener())
    mod.instagram_get('me', 'id,username', TOKEN)
    request, timeout = calls[0]
    assert request.full_url.startswith('https://graph.instagram.com/')
    assert TOKEN not in request.full_url
    assert request.get_header('Authorization') == 'Bearer ' + TOKEN
    assert request.get_method() == 'GET' and timeout <= 10


def test_network_failures_are_sanitized_before_caching(tmp_path, monkeypatch):
    account, mod, config = connection(tmp_path, monkeypatch)
    class Opener:
        def open(self, *args, **kwargs): raise URLError(TOKEN)
    monkeypatch.setattr(mod, 'build_opener', lambda *handlers: Opener())
    result = account.verify()
    assert result['status'] == 'network_unavailable'
    assert TOKEN not in json.dumps(result)
    assert not result['publishing_enabled']


@pytest.mark.asyncio
async def test_instagram_api_is_local_read_only_and_redacts_credentials(tmp_path, monkeypatch):
    mod = module()
    import httpx
    from clipping.app import app
    monkeypatch.setenv('CLIPPING_DATABASE', str(tmp_path / 'jobs.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(tmp_path / 'storage'))
    monkeypatch.setenv('INSTAGRAM_ACCESS_TOKEN', TOKEN)
    monkeypatch.setenv('INSTAGRAM_ACCOUNT_ID', ACCOUNT)
    monkeypatch.setattr(mod, 'instagram_get', verified_response)
    monkeypatch.setattr(ClippingWorkflow, 'consume_once', lambda self: False)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        base = '/api/v1/clipping/accounts/instagram'
        before = await client.get(base)
        assert before.status_code == 200
        response = await client.post(base + '/verify', json={})
        assert response.status_code == 200 and response.json()['status'] == 'verified'
        assert TOKEN not in response.text and TOKEN not in before.text
        assert response.headers['cache-control'] == 'no-store'
        assert (await client.post(base + '/verify', json={},
            headers={'Origin':'https://untrusted.example'})).status_code == 403
        rejected = await client.post(base + '/verify', json={'access_token':TOKEN})
        assert rejected.status_code == 422
        assert TOKEN not in rejected.text, 'Validation errors must not echo a supplied token'
        assert (await client.post(base + '/publish', json={})).status_code == 404
        assert (await client.get('/instagram.js')).status_code == 200


def test_malformed_permission_names_do_not_escape_into_results(tmp_path, monkeypatch):
    account, mod, config = connection(tmp_path, monkeypatch)
    def request(path, fields, token):
        if path == 'me': return verified_response(path, fields, token)
        return {'data': [{'permission': {'access_token': TOKEN}, 'status': 'granted'}]}
    monkeypatch.setattr(mod, 'instagram_get', request)
    state = account.verify()
    assert state['granted_permissions'] == []
    assert state['publishing_enabled'] is False
    assert TOKEN not in json.dumps(state)


def test_expired_token_errors_hide_provider_text(tmp_path, monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError
    account, mod, config = connection(tmp_path, monkeypatch)
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 400, TOKEN, {}, BytesIO(json.dumps(
                {'error': {'code':190,'message':TOKEN}}).encode()))
    monkeypatch.setattr(mod, 'build_opener', lambda *handlers: Opener())
    state = account.verify()
    assert state['status'] == 'token_invalid'
    assert TOKEN not in json.dumps(state)
