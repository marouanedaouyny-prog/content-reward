import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from clipping.instagram import InstagramAPIError, InstagramConnection
from clipping.workflow import ClippingWorkflow

BASE = '/api/v1/clipping/accounts/instagram'
ACCOUNT = '17841400000000001'
TOKEN = 'authorized-token-fixture-1234567890'
SECRET = 'app-secret-fixture-1234567890'
REDIRECT = 'http://127.0.0.1:8000' + BASE + '/callback'


@pytest.fixture
def account(tmp_path, monkeypatch):
    for key in ('INSTAGRAM_APP_ID', 'INSTAGRAM_APP_SECRET', 'INSTAGRAM_REDIRECT_URI',
                'INSTAGRAM_ACCESS_TOKEN', 'INSTAGRAM_ACCOUNT_ID', 'INSTAGRAM_GRAPH_VERSION'):
        monkeypatch.delenv(key, raising=False)
    config = tmp_path / '.env.local'
    config.write_text('INSTAGRAM_APP_ID=1234567890\nINSTAGRAM_APP_SECRET=' + SECRET +
                      '\nINSTAGRAM_REDIRECT_URI=http://127.0.0.1:8000' + BASE + '/callback\n')
    engine = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    return InstagramConnection(engine, config)


def provider(monkeypatch, account, *, username='test.creator', failure=None):
    import clipping.instagram as mod
    requests = []

    def exchange(request):
        requests.append(request)
        if failure:
            raise InstagramAPIError(failure)
        if request.get_method() == 'POST':
            return {'access_token': 'short-token-fixture-1234567890', 'user_id': ACCOUNT}
        return {'access_token': TOKEN, 'token_type': 'bearer', 'expires_in': 5184000}

    def get(path, fields, token):
        assert token == TOKEN
        if path == 'me':
            return {'id': ACCOUNT, 'username': username}
        return {'data': [{'permission': 'instagram_business_basic', 'status': 'granted'}]}

    monkeypatch.setattr(account, '_json_request', exchange)
    monkeypatch.setattr(mod, 'instagram_get', get)
    return requests


@pytest.fixture
def client(account, monkeypatch):
    from clipping.app import app
    # These routes only use the injected connection; no queue consumers run.
    monkeypatch.setattr(app.state, 'instagram', account, raising=False)
    monkeypatch.setenv('INSTAGRAM_REDIRECT_URI', REDIRECT)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000')


@pytest.mark.asyncio
async def test_connect_binds_authorization_to_browser_without_exposing_secrets(client, account):
    async with client:
        response = await client.post(BASE + '/connect', json={})
        assert response.status_code == 200
        url = urlparse(response.json()['authorization_url'])
        assert (url.scheme, url.netloc, url.path) == ('https', 'www.instagram.com', '/oauth/authorize')
        query = parse_qs(url.query)
        assert query['redirect_uri'] == [REDIRECT]
        assert query['scope'] == ['instagram_business_basic,instagram_business_content_publish']
        assert client.cookies['instagram_oauth_state'] == query['state'][0]
        cookie = response.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=lax' in cookie and 'max-age=600' in cookie
        assert response.headers['cache-control'] == 'no-store'
        assert SECRET not in response.text and TOKEN not in response.text
        assert (await client.post(BASE + '/connect', json={},
                headers={'Origin': 'https://untrusted.example'})).status_code == 403
        rejected = await client.post(BASE + '/connect', json={'client_secret': SECRET})
        assert rejected.status_code == 422 and SECRET not in rejected.text


@pytest.mark.asyncio
async def test_callback_saves_verified_identity_and_rejects_replay(client, account, monkeypatch):
    requests = provider(monkeypatch, account)
    async with client:
        started = await client.post(BASE + '/connect', json={})
        assert started.status_code == 200
        state = parse_qs(urlparse(started.json()['authorization_url']).query)['state'][0]
        result = await client.get(BASE + '/callback', params={'state': state, 'code': 'code-fixture'})
        assert result.status_code == 303 and result.headers['location'] == '/?instagram=connected#social-accounts'
        assert 'instagram_oauth_state' not in client.cookies
        status = await client.get(BASE)
        assert status.json()['username'] == 'test.creator'
        assert status.json()['status'] == 'verified' and not status.json()['publishing_enabled']
        assert TOKEN not in status.text and SECRET not in result.text
        body = parse_qs(requests[0].data.decode())
        assert requests[0].full_url == 'https://api.instagram.com/oauth/access_token'
        assert body['redirect_uri'] == [REDIRECT] and body['code'] == ['code-fixture']
        client.cookies.set('instagram_oauth_state', state)
        replay = await client.get(BASE + '/callback', params={'state': state, 'code': 'code-fixture'})
        assert 'oauth_state_invalid' in replay.headers['location']
        assert len(requests) == 2, 'A replay must not exchange another authorization code'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['network_unavailable', 'oauth_failed'])
async def test_callback_failure_keeps_previous_credentials_and_hides_code(client, account, monkeypatch, failure):
    provider(monkeypatch, account, failure=failure)
    with account.engine.connection() as db:
        db.execute('INSERT INTO clipping_setting VALUES (?,?)',
                   ('instagram_oauth_credentials', json.dumps({'token': TOKEN, 'account_id': ACCOUNT})))
    async with client:
        started = await client.post(BASE + '/connect', json={})
        assert started.status_code == 200
        state = parse_qs(urlparse(started.json()['authorization_url']).query)['state'][0]
        result = await client.get(BASE + '/callback', params={'state': state, 'code': 'private-code-fixture'})
        assert result.status_code == 303 and failure in result.headers['location']
        assert 'private-code-fixture' not in result.text + result.headers['location']
        assert 'instagram_oauth_state' not in client.cookies
        assert account._credentials() == (TOKEN, ACCOUNT)


def test_authorized_credentials_replace_stale_file_credentials_as_a_pair(account, monkeypatch):
    provider(monkeypatch, account)
    account.credential_file.write_text(account.credential_file.read_text() +
        'INSTAGRAM_ACCESS_TOKEN=old-token-fixture-1234567890\nINSTAGRAM_ACCOUNT_ID=17841499999999999\n')
    _, state = account.begin_oauth()
    account.complete_oauth(state, state, 'code-fixture')
    assert account._credentials() == (TOKEN, ACCOUNT)
    restored = InstagramConnection(account.engine, account.credential_file)
    assert restored._credentials() == (TOKEN, ACCOUNT)


def test_non_ascii_oauth_state_is_rejected_without_a_server_error(account):
    with pytest.raises(InstagramAPIError, match='expired|validated'):
        account.complete_oauth('é', 'é', 'code-fixture')


def test_malformed_profile_never_replaces_credentials(account, monkeypatch):
    requests = provider(monkeypatch, account, username='invalid username')
    _, state = account.begin_oauth()
    with pytest.raises(InstagramAPIError):
        account.complete_oauth(state, state, 'code-fixture')
    assert len(requests) == 2
    assert not account.status()['configured']


def test_expired_oauth_state_cannot_exchange_code_after_restart(account, monkeypatch):
    requests = provider(monkeypatch, account)
    _, state = account.begin_oauth()
    with account.engine.connection() as db:
        assert db.execute("SELECT count(*) FROM clipping_setting WHERE key LIKE 'instagram_oauth_state:%'").fetchone()[0] == 1
        db.execute('UPDATE clipping_setting SET value=? WHERE key=?',
                   (json.dumps({'created_at': 0}), 'instagram_oauth_state:' + hashlib.sha256(state.encode()).hexdigest()))
    restored = InstagramConnection(account.engine, account.credential_file)
    with pytest.raises(InstagramAPIError, match='expired|validated'):
        restored.complete_oauth(state, state, 'code-fixture')
    assert requests == []


@pytest.mark.asyncio
async def test_provider_denial_consumes_browser_state_without_exchanging_code(client, account, monkeypatch):
    requests = provider(monkeypatch, account)
    async with client:
        response = await client.post(BASE + '/connect', json={})
        assert response.status_code == 200
        state = parse_qs(urlparse(response.json()['authorization_url']).query)['state'][0]
        denied = await client.get(BASE + '/callback', params={'state': state, 'error': 'access_denied',
                                'error_description': SECRET})
        assert denied.status_code == 303 and 'access_denied' in denied.headers['location']
        assert SECRET not in denied.text + denied.headers['location']
        assert 'instagram_oauth_state' not in client.cookies
        assert requests == []
        assert not account._consume_oauth_state(state, state)


@pytest.mark.asyncio
async def test_callback_requires_original_browser_cookie(client, account, monkeypatch):
    requests = provider(monkeypatch, account)
    async with client:
        response = await client.post(BASE + '/connect', json={})
        assert response.status_code == 200
        state = parse_qs(urlparse(response.json()['authorization_url']).query)['state'][0]
        client.cookies.clear()
        result = await client.get(BASE + '/callback', params={'state': state, 'code': 'code-fixture'})
        assert result.status_code == 303 and 'oauth_state_invalid' in result.headers['location']
        assert requests == []


@pytest.mark.parametrize('uri', ['http://outside.example/callback',
    'https://user:password@example.com/callback', 'https://example.com/callback?next=other',
    'https://[invalid', 'http://127.0.0.1:invalid' + BASE + '/callback'])
def test_invalid_redirect_configuration_disables_authorization(account, monkeypatch, uri):
    monkeypatch.setenv('INSTAGRAM_REDIRECT_URI', uri)
    assert not account.oauth_ready()


@pytest.mark.asyncio
async def test_connect_rejects_redirect_on_a_different_browser_host(client, account, monkeypatch):
    monkeypatch.setenv('INSTAGRAM_REDIRECT_URI', 'http://localhost:8000' + BASE + '/callback')
    async with client:
        result = await client.post(BASE + '/connect', json={})
        assert result.status_code == 409
        assert result.json()['status'] == 'oauth_redirect_mismatch'
        assert 'set-cookie' not in result.headers


@pytest.mark.asyncio
async def test_https_connect_uses_a_secure_state_cookie(client, monkeypatch):
    async with client:
        from clipping.app import app
        monkeypatch.setenv('INSTAGRAM_REDIRECT_URI', 'https://workspace.example' + BASE + '/callback')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='https://workspace.example') as secured:
            result = await secured.post(BASE + '/connect', json={})
            assert result.status_code == 200 and 'secure' in result.headers['set-cookie'].lower()


@pytest.mark.asyncio
async def test_callback_removes_authorization_query_before_access_logging(client):
    from clipping.app import app
    scopes = []

    async def capture_scope(scope, receive, send):
        await app(scope, receive, send)
        scopes.append(scope)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=capture_scope),
                                 base_url='http://127.0.0.1:8000') as logged:
        result = await logged.get(BASE + '/callback', params={'state': 'invalid', 'code': 'private-code-fixture'})
        assert result.status_code == 303
        assert b'private-code-fixture' not in scopes[-1]['query_string']


@pytest.fixture
def account_clock(monkeypatch):
    import clipping.instagram as mod

    class Clock(datetime):
        current = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(mod, 'datetime', Clock)
    return Clock


def authorize(account, monkeypatch):
    provider(monkeypatch, account)
    _, state = account.begin_oauth()
    account.complete_oauth(state, state, 'code-fixture')


def test_provider_expiry_is_saved_without_exposing_token_and_survives_restart(account, monkeypatch, account_clock):
    authorize(account, monkeypatch)
    result = InstagramConnection(account.engine, account.credential_file).status()
    assert result['token_expires_at'] == '2026-12-11T12:00:00+00:00'
    assert result['token_expired'] is False
    assert TOKEN not in json.dumps(result)


def test_slow_previous_account_check_cannot_overwrite_reconnected_account(account, monkeypatch):
    import clipping.instagram as mod
    old_token = 'old-token-fixture-1234567890'
    old_id = '17841499999999999'
    with account.engine.connection() as db:
        db.execute('INSERT INTO clipping_setting VALUES (?,?)',
                   ('instagram_oauth_credentials', json.dumps({'token': old_token, 'account_id': old_id})))
    provider(monkeypatch, account)
    pending, resume = threading.Event(), threading.Event()

    def response(path, fields, token):
        if path == 'me':
            return {'id': old_id if token == old_token else ACCOUNT,
                    'username': 'old.creator' if token == old_token else 'new.creator'}
        if token == old_token:
            pending.set()
            assert resume.wait(5), 'The old provider fixture was not released'
        return {'data': [{'permission': 'instagram_business_basic', 'status': 'granted'}]}

    monkeypatch.setattr(mod, 'instagram_get', response)
    with ThreadPoolExecutor(max_workers=1) as executor:
        previous = executor.submit(account.verify)
        try:
            assert pending.wait(5), 'The previous verification did not start'
            _, state = account.begin_oauth()
            account.complete_oauth(state, state, 'code-fixture')
            restarted = InstagramConnection(account.engine, account.credential_file)
            current = restarted.verify()
            assert current['username'] == 'new.creator'
        finally:
            resume.set()
        result = previous.result(timeout=5)
    assert result == current
    assert InstagramConnection(account.engine, account.credential_file).status() == current
    assert TOKEN not in json.dumps(result) and old_token not in json.dumps(result)


def test_in_flight_check_uses_current_expiry_for_the_same_token(account, monkeypatch, account_clock):
    import clipping.instagram as mod
    authorize(account, monkeypatch)

    def response(path, fields, token):
        if path == 'me':
            return {'id': ACCOUNT, 'username': 'test.creator'}
        with account.engine.connection() as db:
            saved = json.loads(db.execute("SELECT value FROM clipping_setting WHERE key='instagram_oauth_credentials'").fetchone()['value'])
            saved['expires_at'] = '2026-12-10T12:00:00+00:00'
            db.execute('UPDATE clipping_setting SET value=? WHERE key=?',
                       (json.dumps(saved), 'instagram_oauth_credentials'))
        return {'data': [{'permission': 'instagram_business_basic', 'status': 'granted'}]}

    monkeypatch.setattr(mod, 'instagram_get', response)
    result = account.verify()
    assert result['token_expires_at'] == '2026-12-10T12:00:00+00:00'
    assert account.status() == result


def test_expired_token_cannot_retain_cached_account_verification(account, monkeypatch, account_clock):
    authorize(account, monkeypatch)
    assert account.verify()['status'] == 'verified'
    account_clock.current = datetime(2026, 12, 11, 12, tzinfo=timezone.utc)
    status = account.status()
    assert status['status'] == 'token_expired'
    assert status['token_expired'] is True
    assert status['username'] is None and not status['permissions_checked']
    assert status['content_publish_permission'] is None and not status['publishing_enabled']


def test_known_expired_token_is_not_sent_to_provider(account, monkeypatch, account_clock):
    import clipping.instagram as mod
    authorize(account, monkeypatch)
    account_clock.current = datetime(2026, 12, 12, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(mod, 'instagram_get', lambda *args: pytest.fail('An expired token was sent'))
    assert account.verify()['status'] == 'token_expired'


def test_token_expiring_during_check_does_not_report_verified(account, monkeypatch, account_clock):
    import clipping.instagram as mod
    authorize(account, monkeypatch)
    account_clock.current = datetime(2026, 12, 11, 11, 59, 59, tzinfo=timezone.utc)

    def response(path, fields, token):
        if path == 'me':
            return {'id': ACCOUNT, 'username': 'test.creator'}
        account_clock.current = datetime(2026, 12, 11, 12, 0, 1, tzinfo=timezone.utc)
        return {'data': [{'permission': 'instagram_business_basic', 'status': 'granted'}]}

    monkeypatch.setattr(mod, 'instagram_get', response)
    result = account.verify()
    assert result['status'] == 'token_expired' and result['token_expired'] is True
    assert result['content_publish_permission'] is None and result['username'] is None


@pytest.mark.parametrize('lifetime', [True, 0, -5, float('inf'), float('nan'), 10 ** 100, SECRET])
def test_invalid_provider_lifetime_does_not_replace_credentials(account, monkeypatch, account_clock, lifetime):
    previous_token = 'previous-token-fixture-1234567890'
    with account.engine.connection() as db:
        db.execute('INSERT INTO clipping_setting VALUES (?,?)',
                   ('instagram_oauth_credentials', json.dumps({'token': previous_token, 'account_id': ACCOUNT})))
    provider(monkeypatch, account)
    exchange = account._json_request
    monkeypatch.setattr(account, '_json_request', lambda request:
        {**exchange(request), 'expires_in': lifetime} if request.get_method() == 'GET' else exchange(request))
    _, state = account.begin_oauth()
    with pytest.raises(InstagramAPIError) as error:
        account.complete_oauth(state, state, 'code-fixture')
    assert SECRET not in str(error.value)
    assert account._credentials() == (previous_token, ACCOUNT)


def test_missing_provider_expiry_stays_unknown(account, monkeypatch, account_clock):
    provider(monkeypatch, account)
    exchange = account._json_request
    monkeypatch.setattr(account, '_json_request', lambda request:
        {key: value for key, value in exchange(request).items() if key != 'expires_in'})
    _, state = account.begin_oauth()
    account.complete_oauth(state, state, 'code-fixture')
    status = account.status()
    assert status['configured']
    assert status['token_expires_at'] is None and status['token_expired'] is None


@pytest.mark.asyncio
async def test_callback_reports_failed_account_check_instead_of_connection_success(client, account, monkeypatch):
    import clipping.instagram as mod
    provider(monkeypatch, account)
    calls = []

    def profile(path, fields, token):
        calls.append(path)
        if len(calls) == 1:
            return {'id': ACCOUNT, 'username': 'test.creator'}
        raise InstagramAPIError('token_invalid')

    monkeypatch.setattr(mod, 'instagram_get', profile)
    async with client:
        started = await client.post(BASE + '/connect', json={})
        state = parse_qs(urlparse(started.json()['authorization_url']).query)['state'][0]
        result = await client.get(BASE + '/callback', params={'state': state, 'code': 'code-fixture'})
        assert result.status_code == 303 and 'instagram=token_invalid' in result.headers['location']
        assert (await client.get(BASE)).json()['status'] == 'token_invalid'
