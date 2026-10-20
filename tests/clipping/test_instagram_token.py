import json

import pytest

from clipping.instagram import InstagramAPIError, InstagramConnection
from clipping.workflow import ClippingWorkflow

TOKEN = 'IGAA-private-token-fixture-1234567890'
ACCOUNT = '17841400000000001'


@pytest.fixture
def account(tmp_path, monkeypatch):
    for key in ('INSTAGRAM_ACCESS_TOKEN', 'INSTAGRAM_ACCOUNT_ID', 'INSTAGRAM_GRAPH_VERSION',
                'INSTAGRAM_APP_ID', 'INSTAGRAM_APP_SECRET', 'INSTAGRAM_REDIRECT_URI'):
        monkeypatch.delenv(key, raising=False)
    return InstagramConnection(ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage'),
                               tmp_path / '.env.local')


def connector():
    from clipping.instagram_token import connect_token
    return connect_token


def test_direct_token_connection_derives_identity_and_persists_verified_access(account, monkeypatch):
    import clipping.instagram as provider

    def get(path, fields, token):
        assert token == TOKEN
        if path == 'me':
            return {'id': ACCOUNT, 'username': 'fixture.creator'}
        return {'data': [{'permission': 'instagram_business_basic', 'status': 'granted'},
                         {'permission': 'instagram_business_content_publish', 'status': 'granted'}]}

    monkeypatch.setattr(provider, 'instagram_get', get)
    state = connector()(account, TOKEN)
    assert state['status'] == 'verified' and state['account_id'] == ACCOUNT
    assert state['content_publish_permission'] is True and state['publishing_enabled'] is False
    assert state['token_expires_at'] is None
    assert TOKEN not in json.dumps(state)
    restored = InstagramConnection(account.engine, account.credential_file)
    assert restored.status()['status'] == 'verified'
    assert restored._credentials() == (TOKEN, ACCOUNT)
    assert not account.credential_file.exists()


@pytest.mark.parametrize('failure', ['token_invalid', 'network_unavailable'])
def test_failed_token_check_preserves_previous_access_pair(account, monkeypatch, failure):
    import clipping.instagram as provider
    previous = {'token': 'previous-token-fixture-1234567890', 'account_id': '17841400000000002'}
    with account.engine.connection() as db:
        db.execute('INSERT INTO clipping_setting VALUES (?, ?)', ('instagram_oauth_credentials', json.dumps(previous)))

    def get(*args):
        raise InstagramAPIError(failure)

    monkeypatch.setattr(provider, 'instagram_get', get)
    with pytest.raises(InstagramAPIError) as error:
        connector()(account, TOKEN)
    assert error.value.code == failure
    assert account._saved_oauth() == previous


def test_malformed_profile_does_not_save_a_token(account, monkeypatch):
    import clipping.instagram as provider
    monkeypatch.setattr(provider, 'instagram_get', lambda *args: {'id': ACCOUNT, 'username': 'invalid/username'})
    with pytest.raises(InstagramAPIError) as error:
        connector()(account, TOKEN)
    assert error.value.code == 'response_invalid' and not account._saved_oauth()


def test_reimporting_same_token_preserves_its_known_expiry(account, monkeypatch):
    import clipping.instagram as provider
    saved = {'token': TOKEN, 'account_id': ACCOUNT, 'expires_at': '2099-01-01T00:00:00+00:00'}
    with account.engine.connection() as db:
        db.execute('INSERT INTO clipping_setting VALUES (?, ?)', ('instagram_oauth_credentials', json.dumps(saved)))

    def get(path, fields, token):
        if path == 'me':
            return {'id': ACCOUNT, 'username': 'fixture.creator'}
        raise InstagramAPIError('permissions_unavailable')

    monkeypatch.setattr(provider, 'instagram_get', get)
    state = connector()(account, TOKEN)
    assert state['status'] == 'profile_verified' and not state['permissions_checked']
    assert state['token_expires_at'] == saved['expires_at']
    assert account._saved_oauth() == saved


def test_invalid_token_syntax_makes_no_provider_call_and_saves_nothing(account, monkeypatch):
    import clipping.instagram as provider
    monkeypatch.setattr(provider, 'instagram_get', lambda *args: pytest.fail('Invalid token reached provider'))
    with pytest.raises(InstagramAPIError):
        connector()(account, 'not-a-valid-token\nprivate-fixture-secret')
    assert not account._saved_oauth()
