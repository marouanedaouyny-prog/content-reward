"""Connect a Meta-generated Instagram user token without a public callback."""

import argparse
import getpass
import json
import os
import re
import sqlite3
import sys
import warnings
from pathlib import Path

from clipping import instagram as provider
from clipping.instagram_tunnel import emit


def connect_token(account, token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{20,4096}', token):
        raise provider.InstagramAPIError('configuration_error')
    profile = provider.instagram_get('me', 'id,username', token)
    identifier = str(profile.get('user_id') or profile.get('id') or '')
    username = profile.get('username')
    if (not re.fullmatch(r'\d{3,30}', identifier) or not isinstance(username, str)
            or not re.fullmatch(r'[A-Za-z0-9_.]{1,30}', username)):
        raise provider.InstagramAPIError('response_invalid')
    # Confirm the account before replacing any saved credentials. The token
    # and derived account ID are then saved together, as in browser OAuth.
    with account.engine.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        saved = account._saved_oauth(db)
        if saved.get('token') != token or saved.get('account_id') != identifier:
            saved = {'token': token, 'account_id': identifier, 'expires_at': None}
        db.execute('INSERT OR REPLACE INTO clipping_setting VALUES (?,?)',
                   ('instagram_oauth_credentials', json.dumps(saved)))
        db.execute("DELETE FROM clipping_setting WHERE key='instagram_verification'")
        db.commit()
    return account.verify()


def main(argv=None):
    from clipping.workflow import ClippingWorkflow

    parser = argparse.ArgumentParser(description='Connect an Instagram user token from Meta using a hidden local prompt.')
    _, unknown = parser.parse_known_args(argv)
    if unknown:
        emit({'status': 'setup_blocked', 'method': 'direct_token', 'reason': 'unsupported_arguments',
              'message': 'Run without arguments. Paste the token only into the hidden prompt.',
              'live_authorization_verified': False})
        return 2
    if not sys.stdin.isatty():
        emit({'status': 'setup_blocked', 'method': 'direct_token', 'reason': 'interactive_terminal_required',
              'message': 'Run connect-instagram-token.ps1 in a normal PowerShell terminal to use the hidden prompt.',
              'live_authorization_verified': False})
        return 1
    try:
        print('Use an Instagram user access token generated for your account in Meta. Paste it here, never in chat.', flush=True)
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            token = getpass.getpass('Instagram access token (hidden): ').strip()
        root = Path(__file__).resolve().parents[1]
        account = provider.InstagramConnection(ClippingWorkflow(
            os.environ.get('CLIPPING_DATABASE', root / 'data/clipping.db'),
            os.environ.get('CLIPPING_STORAGE', root / 'storage/clipping')), root / '.env.local')
        state = connect_token(account, token)
        verified = state['status'] in ('verified', 'profile_verified')
        emit({'status': 'authorized' if verified else 'setup_blocked', 'method': 'direct_token',
              'account_status': state['status'], 'username': state['username'],
              'content_publish_permission': state['content_publish_permission'],
              'token_expires_at': state['token_expires_at'], 'publishing_enabled': False,
              'live_authorization_verified': verified, 'message': state['message']})
        return 0 if verified else 1
    except provider.InstagramAPIError as exc:
        emit({'status': 'setup_blocked', 'method': 'direct_token', 'reason': exc.code,
              'message': str(exc), 'live_authorization_verified': False})
        return 1
    except (OSError, ValueError, sqlite3.Error, getpass.GetPassWarning):
        emit({'status': 'setup_blocked', 'method': 'direct_token', 'reason': 'local_setup_failed',
              'message': 'The local token setup could not complete. Use a normal PowerShell terminal and check workspace access.',
              'live_authorization_verified': False})
        return 1
    except (EOFError, KeyboardInterrupt):
        emit({'status': 'setup_stopped', 'method': 'direct_token', 'live_authorization_verified': False})
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
