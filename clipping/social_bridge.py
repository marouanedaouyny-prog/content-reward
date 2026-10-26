"""Optional local PHP companion for TikTok OAuth and read-only identity checks.

No browser, callback listener, credential persistence, or publishing is implicit.
Install the companion with scripts/setup-social-php.ps1 before use.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class SocialBridgeError(ValueError):
    """Sanitized error safe for local CLI output."""


@dataclass
class TikTokLogin:
    url: str
    client_key: str
    redirect_uri: str
    state: str = field(repr=False)
    verifier: str = field(repr=False)
    created_at: float = field(default_factory=time.monotonic, repr=False)
    consumed: bool = field(default=False, repr=False)


class SocialBridge:
    def __init__(self, *, php: Path | None = None, entry: Path | None = None):
        root = Path(__file__).resolve().parents[1]
        self.php = Path(php or os.environ.get('CONTENT_REWARD_PHP') or root / '.tools/php/php.exe')
        self.entry = Path(entry or os.environ.get('CONTENT_REWARD_PHP_BRIDGE') or
                          root / 'integrations/social-php/bridge.php')

    def _call(self, action: str, **params) -> dict:
        payload = json.dumps({'protocol': 1, 'action': action, 'params': params}, ensure_ascii=True)
        if len(payload) > 65536:
            raise SocialBridgeError('Bridge request too large')
        try:
            result = subprocess.run(
                [str(self.php.resolve()), str(self.entry.resolve())], input=payload,
                capture_output=True, text=True, encoding='utf-8', timeout=35, shell=False,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except subprocess.TimeoutExpired:
            raise SocialBridgeError('PHP bridge timeout') from None
        except OSError:
            raise SocialBridgeError('PHP bridge unavailable; run scripts/setup-social-php.ps1') from None
        try:
            if len(result.stdout) > 1048576:
                raise ValueError()
            reply = json.loads(result.stdout)
            if not isinstance(reply, dict) or reply.get('protocol') != 1:
                raise ValueError()
        except (ValueError, TypeError):
            raise SocialBridgeError('Invalid PHP bridge response') from None
        if result.returncode or reply.get('ok') is not True:
            code = reply.get('error')
            if code not in ('INVALID_REQUEST', 'ACTION_DISABLED', 'REMOTE_ERROR', 'NETWORK_ERROR'):
                code = 'BRIDGE_ERROR'
            raise SocialBridgeError(f'PHP bridge: {code}')
        if not isinstance(reply.get('data'), dict):
            raise SocialBridgeError('Invalid PHP bridge response')
        return reply['data']

    def health(self) -> dict:
        """Offline installation check. Does not verify an account."""
        return self._call('health')

    def start_login(self, client_key: str, redirect_uri: str) -> TikTokLogin:
        """Build an SDK authorization URL offline; caller handles the browser/callback."""
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        data = self._call('authorize_url', client_key=client_key, redirect_uri=redirect_uri,
                          state=state, code_verifier=verifier)
        return TikTokLogin(data['url'], client_key, redirect_uri, state, verifier)

    def complete_login(self, login: TikTokLogin, callback_url: str, client_secret: str) -> dict:
        """Validate a one-use callback then exchange its code. Returns sensitive tokens."""
        if login.consumed or time.monotonic() - login.created_at > 600:
            raise SocialBridgeError('Login expired or already consumed')
        try:
            callback, expected = urlsplit(callback_url), urlsplit(login.redirect_uri)
            params = parse_qs(callback.query, strict_parsing=True, max_num_fields=16)
            same_target = (callback.scheme, callback.netloc, callback.path) == (
                expected.scheme, expected.netloc, expected.path)
            state = params.get('state', [])
            code = params.get('code', [])
            valid = (same_target and not callback.fragment and len(state) == len(code) == 1
                     and hmac.compare_digest(state[0].encode(), login.state.encode())
                     and 'error' not in params)
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise SocialBridgeError('Invalid TikTok callback')
        login.consumed = True
        return self._call('exchange', client_key=login.client_key, client_secret=client_secret,
                          redirect_uri=login.redirect_uri, code=code[0], code_verifier=login.verifier)

    def refresh(self, client_key: str, client_secret: str, refresh_token: str) -> dict:
        """Explicit network request. Persist returned replacement tokens securely."""
        return self._call('refresh', client_key=client_key, client_secret=client_secret,
                          refresh_token=refresh_token)

    def profile(self, access_token: str) -> dict:
        """Explicit read-only request for open_id and display_name."""
        return self._call('profile', access_token=access_token)


def main() -> int:
    """Only expose a safe offline status command at the terminal."""
    try:
        print(json.dumps(SocialBridge().health(), indent=2))
        return 0
    except SocialBridgeError as error:
        print(json.dumps({'status': 'unavailable', 'message': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
