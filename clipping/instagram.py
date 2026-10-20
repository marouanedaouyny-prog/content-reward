"""Instagram Login OAuth and account verification; credentials stay server-side."""

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MESSAGES = {
    'unverified': 'Instagram credentials are saved. Verify the account to check access.',
    'not_configured': 'Save the Instagram access token and account ID in local configuration.',
    'oauth_not_configured': 'Add the Instagram app ID, app secret and registered redirect URI to server configuration.',
    'oauth_redirect_mismatch': 'Open the workspace using the same address as the registered Instagram redirect URI, then connect again.',
    'oauth_state_invalid': 'The Instagram authorization expired or could not be validated. Start again.',
    'oauth_failed': 'Instagram authorization could not be completed. Check the Meta app setup and try again.',
    'configuration_error': 'Check the Instagram account ID, token and optional API version in local configuration.',
    'verified': 'Account identity and basic access were verified. Publishing remains disabled.',
    'profile_verified': 'Account identity was verified. Publishing permissions still need confirmation.',
    'account_mismatch': 'The token identifies a different account ID. Confirm the intended Instagram account.',
    'network_unavailable': 'Instagram could not be reached. Check network access, then verify again.',
    'token_invalid': 'Instagram refused the token. Replace it with a valid token, then verify again.',
    'token_expired': 'The saved Instagram token has expired. Reconnect Instagram to restore account access.',
    'access_denied': 'Instagram refused account access. Check the app and granted permissions.',
    'rate_limited': 'Instagram rate-limited the check. Wait before verifying again.',
    'provider_unavailable': 'Instagram is temporarily unavailable. Verify again later.',
    'response_invalid': 'Instagram returned an unexpected profile response. Verify again later.',
    'permissions_unavailable': 'The account is readable, but its permission list could not be confirmed.',
}


class InstagramAPIError(Exception):
    def __init__(self, code):
        self.code = code if code in MESSAGES else 'provider_unavailable'
        super().__init__(MESSAGES[self.code])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None  # Never forward the bearer credential to a redirected host.


def instagram_get(path, fields, token):
    if path not in ('me', 'me/permissions'):
        raise InstagramAPIError('configuration_error')
    version = os.environ.get('INSTAGRAM_GRAPH_VERSION', '').strip()
    if version and not re.fullmatch(r'v\d{1,3}\.\d', version):
        raise InstagramAPIError('configuration_error')
    prefix = version + '/' if version else ''
    query = '?' + urlencode({'fields': fields}) if fields else ''
    request = Request('https://graph.instagram.com/' + prefix + path + query,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}, method='GET')
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise InstagramAPIError('response_invalid')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise InstagramAPIError('response_invalid')
        if 'error' in result:
            code = result['error'].get('code') if isinstance(result['error'], dict) else None
            raise InstagramAPIError('token_invalid' if code == 190 else 'access_denied')
        return result
    except HTTPError as exc:
        meta_code = None
        try:
            body = json.loads(exc.read(50_000))
            meta_code = body.get('error', {}).get('code')
        except (ValueError, AttributeError):
            pass
        code = ('token_invalid' if meta_code == 190 or exc.code == 401 else
                'rate_limited' if exc.code == 429 or meta_code in (4, 17, 32, 613) else
                'provider_unavailable' if exc.code >= 500 else 'access_denied')
        raise InstagramAPIError(code) from None
    except (URLError, TimeoutError, OSError):
        raise InstagramAPIError('network_unavailable') from None
    except (ValueError, TypeError):
        raise InstagramAPIError('response_invalid') from None


class InstagramConnection:
    def __init__(self, engine, credential_file=None):
        self.engine = engine
        self.credential_file = Path(credential_file) if credential_file else Path(__file__).resolve().parents[1] / '.env.local'
        self._verification_lock = threading.Lock()

    def _saved_oauth(self, db=None):
        if db is None:
            with self.engine.connection() as db:
                return self._saved_oauth(db)
        row = db.execute("SELECT value FROM clipping_setting WHERE key='instagram_oauth_credentials'").fetchone()
        return json.loads(row['value']) if row else {}

    def _credentials(self, db=None):
        values = self._config_values()
        saved = self._saved_oauth(db)
        if saved.get('token') and saved.get('account_id'):
            return saved['token'].strip(), saved['account_id'].strip()
        token = os.environ.get('INSTAGRAM_ACCESS_TOKEN') or values.get('INSTAGRAM_ACCESS_TOKEN') or saved.get('token', '')
        identifier = os.environ.get('INSTAGRAM_ACCOUNT_ID') or values.get('INSTAGRAM_ACCOUNT_ID') or saved.get('account_id', '')
        return token.strip(), identifier.strip()

    def _config_values(self):
        values = {}
        if self.credential_file.is_file():
            for line in self.credential_file.read_text(encoding='utf-8-sig').splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    key, value = line.split('=', 1)
                    values[key.strip()] = value.strip().strip('"\'')
        return values

    def _setting(self, name):
        values = self._config_values()
        return (os.environ.get(name) or values.get(name, '')).strip()

    def oauth_ready(self):
        client_id = self._setting('INSTAGRAM_APP_ID')
        secret = self._setting('INSTAGRAM_APP_SECRET')
        try:
            parsed = urlparse(self.oauth_redirect_uri())
            if parsed.port == 0:
                return False
        except ValueError:
            return False
        valid_uri = (parsed.scheme == 'https' and bool(parsed.hostname) or
                     parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))
        return bool(re.fullmatch(r'\d{5,30}', client_id) and len(secret) >= 20 and valid_uri
                    and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                    and parsed.path == '/api/v1/clipping/accounts/instagram/callback')

    def oauth_redirect_uri(self):
        return self._setting('INSTAGRAM_REDIRECT_URI') or 'http://127.0.0.1:8000/api/v1/clipping/accounts/instagram/callback'

    def begin_oauth(self):
        if not self.oauth_ready():
            raise InstagramAPIError('oauth_not_configured')
        client_id = self._setting('INSTAGRAM_APP_ID')
        redirect_uri = self.oauth_redirect_uri()
        state = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).timestamp()
        with self.engine.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute("SELECT key,value FROM clipping_setting WHERE key LIKE 'instagram_oauth_state:%'").fetchall():
                try:
                    if float(json.loads(row['value']).get('created_at', 0)) < now - 600:
                        db.execute('DELETE FROM clipping_setting WHERE key=?', (row['key'],))
                except (ValueError, TypeError, json.JSONDecodeError):
                    db.execute('DELETE FROM clipping_setting WHERE key=?', (row['key'],))
            db.execute('INSERT INTO clipping_setting VALUES (?,?)',
                       ('instagram_oauth_state:' + hashlib.sha256(state.encode()).hexdigest(), json.dumps({'created_at': now})))
            db.commit()
        params = urlencode({'client_id': client_id, 'redirect_uri': redirect_uri,
            'response_type': 'code', 'scope': 'instagram_business_basic,instagram_business_content_publish', 'state': state})
        return 'https://www.instagram.com/oauth/authorize?' + params, state

    def _consume_oauth_state(self, state, cookie_state):
        if (not isinstance(state, str) or not isinstance(cookie_state, str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{43}', state)
                or not re.fullmatch(r'[A-Za-z0-9_-]{43}', cookie_state)
                or not hmac.compare_digest(state, cookie_state)):
            return False
        key = 'instagram_oauth_state:' + hashlib.sha256(state.encode()).hexdigest()
        with self.engine.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM clipping_setting WHERE key=?', (key,)).fetchone()
            db.execute('DELETE FROM clipping_setting WHERE key=?', (key,))
            db.commit()
        if not row:
            return False
        try:
            return float(json.loads(row['value']).get('created_at', 0)) >= datetime.now(timezone.utc).timestamp() - 600
        except (ValueError, TypeError, json.JSONDecodeError):
            return False

    @staticmethod
    def _json_request(request):
        try:
            with build_opener(NoRedirect()).open(request, timeout=12) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise InstagramAPIError('oauth_failed')
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get('error'):
                raise InstagramAPIError('oauth_failed')
            return result
        except HTTPError:
            raise InstagramAPIError('oauth_failed') from None
        except (URLError, TimeoutError, OSError):
            raise InstagramAPIError('network_unavailable') from None
        except (ValueError, TypeError):
            raise InstagramAPIError('oauth_failed') from None

    def complete_oauth(self, state, cookie_state, code):
        if not self._consume_oauth_state(state, cookie_state):
            raise InstagramAPIError('oauth_state_invalid')
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9._~#-]{1,4096}', code):
            raise InstagramAPIError('oauth_failed')
        if not self.oauth_ready():
            raise InstagramAPIError('oauth_not_configured')
        client_id = self._setting('INSTAGRAM_APP_ID')
        client_secret = self._setting('INSTAGRAM_APP_SECRET')
        redirect_uri = self.oauth_redirect_uri()
        body = urlencode({'client_id': client_id, 'client_secret': client_secret,
            'grant_type': 'authorization_code', 'redirect_uri': redirect_uri, 'code': code}).encode()
        short_response = self._json_request(Request('https://api.instagram.com/oauth/access_token', data=body,
            headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}, method='POST'))
        short_token = short_response.get('access_token')
        if not isinstance(short_token, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{20,4096}', short_token):
            raise InstagramAPIError('oauth_failed')
        long_url = 'https://graph.instagram.com/access_token?' + urlencode({
            'grant_type': 'ig_exchange_token', 'client_secret': client_secret, 'access_token': short_token})
        issued_at = datetime.now(timezone.utc)
        long_response = self._json_request(Request(long_url, headers={'Accept': 'application/json'}, method='GET'))
        token = long_response.get('access_token')
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{20,4096}', token):
            raise InstagramAPIError('oauth_failed')
        # OAuth expires_in is a duration in seconds. Start before the exchange
        # so transport time cannot extend the recorded lifetime.
        # https://www.rfc-editor.org/rfc/rfc6749#section-5.1
        expires_at = None
        if 'expires_in' in long_response:
            lifetime = long_response['expires_in']
            if type(lifetime) is not int or lifetime <= 0:
                raise InstagramAPIError('oauth_failed')
            try:
                expires_at = (issued_at + timedelta(seconds=lifetime)).isoformat()
            except OverflowError:
                raise InstagramAPIError('oauth_failed') from None
        profile = instagram_get('me', 'id,username', token)
        identifier = str(profile.get('user_id') or profile.get('id') or '')
        username = profile.get('username')
        if (not re.fullmatch(r'\d{3,30}', identifier) or not isinstance(username, str)
                or not re.fullmatch(r'[A-Za-z0-9_.]{1,30}', username)):
            raise InstagramAPIError('oauth_failed')
        with self.engine.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO clipping_setting VALUES (?,?)',
                       ('instagram_oauth_credentials', json.dumps({'token': token, 'account_id': identifier,
                           'issued_at': issued_at.isoformat(), 'expires_at': expires_at})))
            db.execute("DELETE FROM clipping_setting WHERE key='instagram_verification'")
            db.commit()

    @staticmethod
    def _fingerprint(token, identifier):
        return hashlib.sha256((token + '\n' + identifier + '\n' + os.environ.get('INSTAGRAM_GRAPH_VERSION', '')).encode()).hexdigest()

    def _initial(self, token, identifier, db=None):
        configured = bool(token and identifier)
        valid = bool(re.fullmatch(r'[A-Za-z0-9_.-]{20,4096}', token) and re.fullmatch(r'\d{3,30}', identifier))
        status = 'unverified' if valid else 'configuration_error' if configured else 'not_configured'
        expires_at, expired = self._expiry(token, identifier, db)
        if valid and expired:
            status = 'token_expired'
        oauth_configured = self.oauth_ready()
        return {'configured': configured, 'status': status,
            'oauth_configured': oauth_configured,
            'account_id': identifier if re.fullmatch(r'\d{3,30}', identifier) else None,
            'returned_account_id': None, 'username': None, 'permissions_checked': False,
            'content_publish_permission': None, 'granted_permissions': [],
            'token_expires_at': expires_at, 'token_expired': expired,
            'publishing_enabled': False, 'last_checked_at': None,
            'message': 'Connect Instagram to authorize this workspace. No account token is saved yet.'
                if status == 'not_configured' and oauth_configured else MESSAGES[status]}

    def _expiry(self, token, identifier, db=None):
        saved = self._saved_oauth(db)
        if saved.get('token') != token or saved.get('account_id') != identifier or not saved.get('expires_at'):
            return None, None
        try:
            date = datetime.fromisoformat(saved['expires_at'])
            if date.tzinfo is None:
                return None, None
            date = date.astimezone(timezone.utc)
            return date.isoformat(), date <= datetime.now(timezone.utc)
        except (ValueError, TypeError):
            return None, None

    def status(self):
        with self.engine.connection() as db:
            db.execute('BEGIN')
            return self._status(db, *self._credentials(db))

    def _status(self, db, token, identifier):
        initial = self._initial(token, identifier, db)
        if initial['status'] != 'unverified':
            return initial
        row = db.execute("SELECT value FROM clipping_setting WHERE key='instagram_verification'").fetchone()
        if row:
            saved = json.loads(row['value'])
            if saved.get('fingerprint') == self._fingerprint(token, identifier):
                return {**initial, **{key: saved['status'][key] for key in initial if key in saved['status']},
                        'oauth_configured': initial['oauth_configured'],
                        'token_expires_at': initial['token_expires_at'], 'token_expired': initial['token_expired'],
                        'publishing_enabled': False}
        return initial

    def verify(self):
        # Serialize this instance's provider checks. Reconnection can also write
        # through another instance, so the final save must compare credentials.
        with self._verification_lock:
            with self.engine.connection() as db:
                db.execute('BEGIN')
                token, identifier = self._credentials(db)
                state = self._initial(token, identifier, db)
                fingerprint = self._fingerprint(token, identifier)
            if state['status'] != 'unverified':
                return state
            state['last_checked_at'] = datetime.now(timezone.utc).isoformat()
            try:
                profile = instagram_get('me', 'id,username', token)
                returned = str(profile.get('user_id') or profile.get('id') or '')
                username = profile.get('username')
                if not re.fullmatch(r'\d{3,30}', returned) or not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,30}', username):
                    raise InstagramAPIError('response_invalid')
                state['returned_account_id'] = returned
                if returned != identifier:
                    state['status'] = 'account_mismatch'
                else:
                    state['username'] = username
                    state['status'] = 'profile_verified'
                    try:
                        permissions = instagram_get('me/permissions', '', token).get('data')
                        if isinstance(permissions, list) and all(isinstance(item, dict) for item in permissions):
                            known = {'instagram_business_basic', 'instagram_business_content_publish',
                                     'instagram_business_manage_comments', 'instagram_business_manage_messages'}
                            state['granted_permissions'] = sorted({item.get('permission') for item in permissions
                                if item.get('status') == 'granted' and isinstance(item.get('permission'), str)
                                and item.get('permission') in known})
                            state['permissions_checked'] = True
                            state['content_publish_permission'] = 'instagram_business_content_publish' in state['granted_permissions']
                            if 'instagram_business_basic' in state['granted_permissions']:
                                state['status'] = 'verified'
                    except InstagramAPIError as exc:
                        if exc.code == 'token_invalid':
                            raise
                        # Account readability does not establish publishing access.
                        state['permissions_checked'] = False
            except InstagramAPIError as exc:
                state['status'] = exc.code
                state['content_publish_permission'] = None
            with self.engine.connection() as db:
                # Keep comparison and save in one short transaction; never hold
                # a database write lock while waiting for the provider.
                db.execute('BEGIN IMMEDIATE')
                current_token, current_id = self._credentials(db)
                if fingerprint != self._fingerprint(current_token, current_id):
                    return self._status(db, current_token, current_id)
                current = self._initial(current_token, current_id, db)
                if current['token_expired']:
                    state = {**current, 'last_checked_at': state['last_checked_at']}
                else:
                    for key in ('oauth_configured', 'token_expires_at', 'token_expired'):
                        state[key] = current[key]
                state['message'] = MESSAGES[state['status']]
                saved = {'fingerprint': fingerprint, 'status': state}
                db.execute('INSERT OR REPLACE INTO clipping_setting VALUES (?,?)',
                    ('instagram_verification', json.dumps(saved)))
                db.commit()
            return state
