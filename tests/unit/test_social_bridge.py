"""Offline contract tests; never use account credentials or social networks."""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from clipping.social_bridge import SocialBridge, SocialBridgeError


ROOT = Path(__file__).resolve().parents[2]
PHP = ROOT / '.tools/php/php.exe'
ENTRY = ROOT / 'integrations/social-php/bridge.php'


@pytest.fixture
def bridge():
    if not PHP.is_file() or not (ENTRY.parent / 'vendor/autoload.php').is_file():
        pytest.skip('Optional PHP companion not installed; run scripts/setup-social-php.ps1')
    return SocialBridge(php=PHP, entry=ENTRY)


def test_real_python_php_health_and_cli(bridge, capsys):
    from clipping.cli import main
    result = bridge.health()
    assert result['sdk_version'].lstrip('v') == '1.0.5'
    assert result['publishing_enabled'] is False
    assert result['account_verified'] is False
    assert main(['social', 'status']) == 0
    assert json.loads(capsys.readouterr().out)['sdk_loaded'] is True


def test_sdk_login_uses_unique_state_and_tiktok_desktop_pkce(bridge):
    login = bridge.start_login('example-client', 'http://127.0.0.1:8765/callback/')
    parsed = urlsplit(login.url)
    params = parse_qs(parsed.query)
    assert parsed.netloc == 'www.tiktok.com'
    assert params['scope'] == ['user.info.basic']
    assert params['state'] == [login.state]
    assert params['code_challenge_method'] == ['S256']
    assert params['code_challenge'] == [hashlib.sha256(login.verifier.encode()).hexdigest()]
    assert 'verifier' not in repr(login)
    assert login.state != bridge.start_login('example-client', login.redirect_uri).state


@pytest.mark.parametrize('redirect', ['http://evil.example/cb', 'http://localhost/cb',
                                      'https://example.com/cb?q=1', 'https://u:p@example.com/cb'])
def test_invalid_redirects_rejected_offline(bridge, redirect):
    with pytest.raises(SocialBridgeError):
        bridge.start_login('example-client', redirect)


@pytest.mark.parametrize('callback', ['http://evil.example/cb?state=wrong&code=example',
                                     'http://127.0.0.1:8765/callback/?state=wrong&code=example'])
def test_bad_callback_never_exchanges_code(bridge, callback):
    login = bridge.start_login('example-client', 'http://127.0.0.1:8765/callback/')
    with pytest.raises(SocialBridgeError, match='callback'):
        bridge.complete_login(login, callback, 'synthetic-secret')


def test_valid_callback_is_consumed_once(bridge, monkeypatch):
    login = bridge.start_login('example-client', 'http://127.0.0.1:8765/callback/')
    calls = []
    def call(action, **params):
        calls.append((action, params))
        return {'access_token': 'synthetic-token'}
    monkeypatch.setattr(bridge, '_call', call)
    callback = login.redirect_uri + '?' + urlencode({'state': login.state, 'code': 'synthetic-code'})
    assert bridge.complete_login(login, callback, 'synthetic-secret')['access_token'] == 'synthetic-token'
    assert calls[0][1]['code_verifier'] == login.verifier
    with pytest.raises(SocialBridgeError):
        bridge.complete_login(login, callback, 'synthetic-secret')
    assert len(calls) == 1


def test_expired_login_rejected(bridge):
    login = bridge.start_login('example-client', 'https://example.com/callback')
    login.created_at -= 601
    callback = login.redirect_uri + '?' + urlencode({'state': login.state, 'code': 'example'})
    with pytest.raises(SocialBridgeError, match='expired'):
        bridge.complete_login(login, callback, 'synthetic-secret')


@pytest.mark.parametrize('action', ['publish', 'upload', 'draft', 'custom_request'])
def test_php_rejects_publication_and_custom_endpoints(bridge, action):
    with pytest.raises(SocialBridgeError, match='ACTION_DISABLED'):
        bridge._call(action, access_token='synthetic-token', publishing_enabled=True)


@pytest.mark.parametrize('payload', ['not-json', '[]', '{"protocol":2,"action":"health"}', 'x' * 65537],
                         ids=['malformed', 'array', 'wrong-version', 'oversized'])
def test_raw_php_rejects_malformed_protocol(bridge, payload):
    result = subprocess.run([str(PHP), str(ENTRY)], input=payload, text=True, capture_output=True, timeout=5)
    reply = json.loads(result.stdout)
    assert reply['ok'] is False
    assert reply['error'] == 'INVALID_REQUEST'


def test_errors_do_not_echo_secrets_or_subprocess_output(monkeypatch):
    def failed(*args, **kwargs):
        assert 'synthetic-secret' not in repr(args[0])
        return subprocess.CompletedProcess(args[0], 1, 'synthetic-secret', 'synthetic-secret')
    monkeypatch.setattr(subprocess, 'run', failed)
    with pytest.raises(SocialBridgeError) as error:
        SocialBridge().refresh('example-client', 'synthetic-secret', 'synthetic-refresh')
    assert 'synthetic-secret' not in str(error.value)


def test_timeout_is_sanitized(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 35, output='synthetic-secret')
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(SocialBridgeError, match='timeout'):
        SocialBridge().health()


def test_real_sdk_requests_with_fake_http_only(bridge):
    result = subprocess.run([str(PHP), str(ROOT / 'tests/php/social_bridge_test.php')],
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout
