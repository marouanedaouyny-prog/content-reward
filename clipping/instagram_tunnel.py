"""Configure a live HTTPS Instagram callback without exposing credentials."""

import argparse
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import threading
import time
import uuid
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, build_opener, getproxies

from clipping.media import command as agent_command

CALLBACK = '/api/v1/clipping/accounts/instagram/callback'
PROVIDER_HOSTS = ('api.instagram.com', 'graph.instagram.com')
MESSAGES = {
    'proxy_connection_refused': 'The configured proxy refused the connection. Use a terminal with permitted outbound access.',
    'network_unavailable': 'The Instagram services could not be reached from this process.',
    'ngrok_network_unavailable': 'Ngrok could not connect to its cloud service from this process.',
    'agent_too_old': 'Ngrok still rejected the agent version after the automatic update attempt.',
    'agent_update_failed': 'The local ngrok copy could not update. Run ngrok update in your normal terminal, then retry setup.',
    'ngrok_credentials_rejected': 'Ngrok rejected its account credentials. Check the saved ngrok configuration.',
    'configuration_error': 'Ngrok could not read its tunnel configuration.',
    'agent_error': 'Ngrok rejected the connection. Check its reported error code.',
    'agent_stopped': 'Ngrok stopped before it created an HTTPS endpoint.',
    'connection_timeout': 'Ngrok did not create an HTTPS endpoint within the startup deadline.',
}


class TunnelUnavailable(Exception):
    def __init__(self, reason, codes=(), *, stage=None, host=None, failure_type=None, http_status=None):
        self.reason = reason if reason in MESSAGES else 'agent_error'
        self.codes = [code for code in codes if re.fullmatch(r'ERR_NGROK_\d+', code)]
        self.diagnostics = {}
        if stage in ('instagram_preflight', 'ngrok_startup'):
            self.diagnostics['stage'] = stage
        if host in (*PROVIDER_HOSTS, 'ngrok_cloud'):
            self.diagnostics['host'] = host
        if failure_type in ('dns_error', 'tls_error', 'timeout', 'connection_refused',
                            'connection_reset', 'transport_error', 'provider_http_error'):
            self.diagnostics['failure_type'] = failure_type
        if isinstance(http_status, int) and 100 <= http_status <= 599:
            self.diagnostics['http_status'] = http_status
        super().__init__(MESSAGES[self.reason])


def public_origin(value):
    if not isinstance(value, str) or any(ord(character) < 33 for character in value):
        raise ValueError('Use the HTTPS origin returned by ngrok')
    try:
        parsed = urlparse(value)
        valid = (parsed.scheme == 'https' and parsed.hostname and parsed.port in (None, 443)
                 and not parsed.username and not parsed.password and parsed.path in ('', '/')
                 and '?' not in value and '#' not in value
                 and re.fullmatch(r'[A-Za-z0-9.-]{1,253}', parsed.hostname))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Use the HTTPS origin returned by ngrok')
    return value.rstrip('/')


def select_tunnel(data, port=8000):
    if not isinstance(data, dict) or not isinstance(data.get('tunnels'), list):
        return None
    for tunnel in data['tunnels']:
        if not isinstance(tunnel, dict) or not isinstance(tunnel.get('config'), dict):
            continue
        address = tunnel['config'].get('addr', '')
        if not isinstance(address, str):
            continue
        try:
            upstream = urlparse(address if '://' in address else 'http://' + address)
            if (upstream.hostname not in ('localhost', '127.0.0.1', '::1') or upstream.port != port
                    or upstream.username or upstream.password or upstream.path not in ('', '/')
                    or upstream.query or upstream.fragment):
                continue
            return public_origin(tunnel.get('public_url'))
        except ValueError:
            continue
    return None


def configure_redirect(config_path, origin):
    callback = public_origin(origin) + CALLBACK
    config_path = Path(config_path)
    original = config_path.read_bytes() if config_path.exists() else b''
    text = original.decode('utf-8')
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = []
    replaced = False
    for line in text.splitlines(keepends=True):
        if re.match(r'^\ufeff?[ \t]*INSTAGRAM_REDIRECT_URI[ \t]*=', line):
            if not replaced:
                bom = '\ufeff' if line.startswith('\ufeff') else ''
                ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
                lines.append(bom + 'INSTAGRAM_REDIRECT_URI=' + callback + ending)
                replaced = True
        else:
            lines.append(line)
    updated = ''.join(lines)
    if not replaced:
        if updated and not updated.endswith(('\r', '\n')):
            updated += newline
        updated += 'INSTAGRAM_REDIRECT_URI=' + callback + newline
    scratch = config_path.parent / '.workflow-tests'
    scratch.mkdir(exist_ok=True)
    temporary = scratch / ('instagram-config-' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_bytes(updated.encode('utf-8'))
        if os.name != 'nt' and config_path.exists():
            temporary.chmod(stat.S_IMODE(config_path.stat().st_mode))
        if config_path.exists() and config_path.read_bytes() != original:
            raise ValueError('Configuration changed during callback setup. Run setup again.')
        os.replace(temporary, config_path)
    finally:
        temporary.unlink(missing_ok=True)
    return callback


def classify_failure(raw):
    lower = raw.lower()
    codes = sorted(set(re.findall(r'ERR_NGROK_\d+', raw)))
    reason = ('proxy_connection_refused' if 'refused' in lower and '127.0.0.1:9' in lower else
              'agent_too_old' if 'ERR_NGROK_121' in codes or 'too old' in lower and 'version' in lower else
              'ngrok_credentials_rejected' if any(code in codes for code in ('ERR_NGROK_105', 'ERR_NGROK_4018')) else
              'configuration_error' if 'error reading configuration' in lower or 'unknown flag' in lower else
              'agent_error' if codes else
              'network_unavailable' if any(term in lower for term in (
                  'refused', 'timed out', 'timeout', 'no such host', 'lookup ', 'tls', 'x509', 'certificate')) else
              'connection_timeout')
    return {'reason': reason, 'ngrok_error_codes': codes}


def transport_failure(cause):
    if isinstance(cause, socket.gaierror):
        return 'dns_error'
    if isinstance(cause, ssl.SSLError):
        return 'tls_error'
    if isinstance(cause, TimeoutError):
        return 'timeout'
    if isinstance(cause, ConnectionRefusedError):
        return 'connection_refused'
    if isinstance(cause, ConnectionResetError):
        return 'connection_reset'
    detail = str(cause).lower()
    for terms, category in (
        (('no such host', 'getaddrinfo', 'lookup ', 'name resolution'), 'dns_error'),
        (('certificate', 'tls', 'x509', 'ssl'), 'tls_error'),
        (('timed out', 'timeout'), 'timeout'),
        (('refused',), 'connection_refused'),
        (('reset',), 'connection_reset'),
    ):
        if any(term in detail for term in terms):
            return category
    return 'transport_error'


def read_tunnels():
    connection = http.client.HTTPConnection('127.0.0.1', 4040, timeout=.5)
    try:
        connection.request('GET', '/api/tunnels')
        response = connection.getresponse()
        body = response.read(1_000_001)
        if response.status != 200 or len(body) > 1_000_000:
            return {}
        return json.loads(body)
    except (OSError, ValueError, http.client.HTTPException):
        return {}
    finally:
        connection.close()


def wait_for_tunnel(read, exited, logs, timeout=30, port=8000):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        origin = select_tunnel(read(), port)
        if origin:
            return origin
        raw = logs()
        failure = classify_failure(raw)
        if failure['reason'] != 'connection_timeout' or exited():
            reason = failure['reason'] if failure['reason'] != 'connection_timeout' else 'agent_stopped'
            if reason == 'network_unavailable':
                reason = 'ngrok_network_unavailable'
            category = transport_failure(raw) if reason in ('ngrok_network_unavailable', 'proxy_connection_refused') else None
            raise TunnelUnavailable(reason, failure['ngrok_error_codes'], stage='ngrok_startup',
                                    host='ngrok_cloud', failure_type=category)
        time.sleep(.2)
    raise TunnelUnavailable('connection_timeout', stage='ngrok_startup', host='ngrok_cloud', failure_type='timeout')


def check_provider_host(host):
    from clipping.instagram import NoRedirect
    if host not in PROVIDER_HOSTS:
        raise ValueError('Use an Instagram provider host')
    try:
        with build_opener(NoRedirect()).open(Request('https://' + host + '/', method='GET'), timeout=3) as response:
            response.read(0)
    except HTTPError as exc:
        if exc.code >= 500:
            raise TunnelUnavailable('network_unavailable', stage='instagram_preflight', host=host,
                                    failure_type='provider_http_error', http_status=exc.code) from None
        # A 4xx root response still proves transport reaches the provider.
    except (URLError, OSError, TimeoutError) as exc:
        cause = exc.reason if isinstance(exc, URLError) else exc
        detail = f"{type(cause).__name__} {cause} {getproxies().get('https', '')}"
        failure = classify_failure(detail)
        reason = 'proxy_connection_refused' if failure['reason'] == 'proxy_connection_refused' else 'network_unavailable'
        raise TunnelUnavailable(reason, stage='instagram_preflight', host=host,
                                failure_type=transport_failure(cause)) from None


def check_provider_network():
    for host in PROVIDER_HOSTS:
        check_provider_host(host)


def diagnose_setup(executable, saved_config):
    executable, saved_config = Path(executable).resolve(), Path(saved_config).resolve()
    version = None
    if executable.is_file():
        try:
            match = re.search(r'\bngrok version (\d+\.\d+\.\d+)\b',
                              agent_command([str(executable), 'version'], timeout=5, kill_tree=True))
            version = match.group(1) if match else None
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    configuration_valid = False
    if executable.is_file() and saved_config.is_file():
        try:
            agent_command([str(executable), 'config', 'check', '--config', str(saved_config)],
                          timeout=5, kill_tree=True)
            configuration_valid = True
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    checks = []
    for host in PROVIDER_HOSTS:
        try:
            check_provider_host(host)
            checks.append({'host': host, 'status': 'reachable'})
        except TunnelUnavailable as exc:
            checks.append({'status': 'failed', 'reason': exc.reason, **exc.diagnostics})
    return {'status': 'diagnostic_complete', 'ngrok_path': str(executable),
            'ngrok_exists': executable.is_file(), 'ngrok_version': version,
            'ngrok_config_path': str(saved_config), 'ngrok_config_valid': configuration_valid,
            'python_path': str(Path(sys.executable).resolve()),
            'proxy_configured': bool(getproxies().get('https')), 'instagram_checks': checks,
            'live_authorization_verified': False}


def authentication_app(account):
    from fastapi import FastAPI, Request as WebRequest
    from fastapi.responses import HTMLResponse, JSONResponse
    from clipping.instagram_api import router

    app = FastAPI(title='Instagram authentication setup', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.instagram = account
    app.include_router(router)

    @app.middleware('http')
    async def same_origin(request: WebRequest, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin != f'{request.url.scheme}://{request.url.netloc}':
            return JSONResponse({'detail': 'Use the Instagram authentication page'}, status_code=403)
        return await call_next(request)

    @app.get('/', response_class=HTMLResponse)
    def page():
        html = Path(__file__).with_name('instagram-auth.html').read_text(encoding='utf-8')
        return HTMLResponse(html.replace('{{CALLBACK}}', escape(account.oauth_redirect_uri())), headers={
            'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            'X-Content-Type-Options': 'nosniff'})

    return app


def confirm_callback(port, origin):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.request('POST', '/api/v1/clipping/accounts/instagram/connect', body='{}', headers={
            'Host': urlparse(origin).netloc, 'X-Forwarded-Proto': 'https', 'Origin': origin,
            'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = json.loads(response.read(100_000))
        query = parse_qs(urlparse(data.get('authorization_url', '')).query)
        cookie = response.getheader('Set-Cookie', '').lower()
        if (response.status != 200 or query.get('redirect_uri') != [origin + CALLBACK]
                or 'instagram_oauth_state=' not in cookie or 'secure' not in cookie):
            raise ValueError('The HTTPS callback and browser state cookie could not be confirmed')
    finally:
        connection.close()


def emit(result, filename='instagram-authentication-last-run.json'):
    root = Path(__file__).resolve().parents[1] / '.workflow-tests'
    root.mkdir(exist_ok=True)
    (root / filename).write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


def upgrade_agent(executable, cache):
    source = Path(executable).resolve()
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / 'ngrok.exe'
    previous = target.read_bytes() if target.exists() else None
    try:
        if source != target.resolve():
            shutil.copy2(source, target)
        # Ngrok validates the update signature before replacing its executable.
        agent_command([str(target), 'update'], cwd=cache, timeout=120, kill_tree=True)
    except (OSError, ValueError, subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        if previous is not None:
            target.write_bytes(previous)
        elif target.exists():
            shutil.copy2(source, target)
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise TunnelUnavailable('agent_update_failed') from None
    return target


def setup_with_upgrade(account, config_path, executable, saved_config, port=8001, no_browser=False):
    try:
        return run_setup(account, config_path, executable, saved_config, port, no_browser)
    except TunnelUnavailable as exc:
        if exc.reason != 'agent_too_old':
            raise
    emit({'status': 'updating_agent', 'message': 'Updating a project-local ngrok copy, then retrying authentication.',
          'live_authorization_verified': False})
    updated = upgrade_agent(executable, Path(config_path).parent / '.workflow-tests/ngrok-runtime')
    return run_setup(account, config_path, updated, saved_config, port, no_browser)


def run_setup(account, config_path, executable, saved_config, port=8001, no_browser=False):
    import uvicorn
    from clipping.instagram import InstagramAPIError
    from clipping.windows_process import launch

    if not account.oauth_ready():
        raise InstagramAPIError('oauth_not_configured')
    check_provider_network()
    session = Path(__file__).resolve().parents[1] / '.workflow-tests' / ('instagram-auth-' + uuid.uuid4().hex)
    session.mkdir(parents=True)
    tunnel_config = session / 'ngrok.json'
    login_file = session / 'tunnel-login.txt'
    password = secrets.token_urlsafe(24)
    tunnel_config.write_text(json.dumps({'version': '2', 'tunnels': {'instagram': {
        'proto': 'http', 'addr': f'127.0.0.1:{port}', 'schemes': ['https'],
        'host_header': 'preserve', 'inspect': False, 'basic_auth': ['workflow:' + password]}}}), encoding='utf-8')
    login_file.write_text('Username: workflow\nPassword: ' + password + '\n', encoding='utf-8')
    password = None
    server = uvicorn.Server(uvicorn.Config(authentication_app(account), host='127.0.0.1', port=port,
        access_log=False, proxy_headers=True, forwarded_allow_ips='127.0.0.1', log_level='warning'))
    thread = threading.Thread(target=server.run, name='instagram-auth-server', daemon=True)
    before = account.status()
    args = [str(executable), 'start', 'instagram', '--config', str(saved_config),
            '--config', str(tunnel_config), '--log=stdout', '--log-format=json']
    try:
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        if not server.started:
            raise ValueError('The local authentication service could not start. Check its port.')
        with launch(args) as process:
            def logs():
                try:
                    stdout, stderr = process.communicate(timeout=.01)
                    raw = stdout + stderr
                except subprocess.TimeoutExpired as exc:
                    output, error = exc.output or b'', exc.stderr or b''
                    raw = output + error
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8', errors='replace')
                return raw[-65_536:]

            origin = wait_for_tunnel(read_tunnels, lambda: process.poll() is not None, logs, port=port)
            callback = configure_redirect(config_path, origin)
            confirm_callback(port, origin)
            emit({'status': 'callback_ready', 'callback_uri': callback, 'authentication_page': origin,
                  'tunnel_login_file': str(login_file), 'provider_registration_verified': False,
                  'message': 'Save this callback in Meta Instagram login settings, then open the authentication page.',
                  'live_authorization_verified': False})
            if not no_browser:
                import webbrowser
                webbrowser.open(origin)
            deadline = time.monotonic() + 900
            while process.poll() is None and time.monotonic() < deadline:
                current = account.status()
                if (current['status'] in ('verified', 'profile_verified') and current['last_checked_at']
                        and current['last_checked_at'] != before.get('last_checked_at')):
                    emit({'status': 'authorized', 'account_status': current['status'],
                          'content_publish_permission': current['content_publish_permission'],
                          'live_authorization_verified': True, 'publishing_enabled': False,
                          'message': 'Account access is saved in the clipping workspace. Posting remains disabled.'})
                    time.sleep(10)
                    return 0
                time.sleep(.5)
            raise TunnelUnavailable('agent_stopped' if process.poll() is not None else 'connection_timeout')
    finally:
        server.should_exit = True
        if thread.is_alive():
            thread.join(timeout=5)
        for path in (tunnel_config, login_file):
            path.unlink(missing_ok=True)
        session.rmdir()


def main():
    from clipping.instagram import InstagramAPIError, InstagramConnection
    from clipping.workflow import ClippingWorkflow

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description='Start a protected HTTPS Instagram authentication session.')
    parser.add_argument('--ngrok-exe', required=True)
    parser.add_argument('--ngrok-config', default=str(Path(os.environ.get('LOCALAPPDATA', '')) / 'ngrok/ngrok.yml'))
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--diagnose', action='store_true', help='Check paths and provider connectivity without starting login.')
    args = parser.parse_args()
    if args.diagnose:
        emit(diagnose_setup(args.ngrok_exe, args.ngrok_config), 'instagram-network-diagnostic-last-run.json')
        return 0
    account = InstagramConnection(ClippingWorkflow(os.environ.get('CLIPPING_DATABASE', root / 'data/clipping.db'),
        os.environ.get('CLIPPING_STORAGE', root / 'storage/clipping')), root / '.env.local')
    try:
        return setup_with_upgrade(account, root / '.env.local', args.ngrok_exe, args.ngrok_config, args.port, args.no_browser)
    except TunnelUnavailable as exc:
        emit({'status': 'setup_blocked', 'reason': exc.reason, 'ngrok_error_codes': exc.codes,
              **exc.diagnostics,
              'message': str(exc), 'live_authorization_verified': False})
        return 1
    except InstagramAPIError as exc:
        emit({'status': 'setup_blocked', 'reason': exc.code, 'message': str(exc), 'live_authorization_verified': False})
        return 1
    except (OSError, ValueError):
        emit({'status': 'setup_blocked', 'reason': 'local_setup_failed',
              'message': 'The local authentication setup could not complete. Check ngrok configuration and the local port.',
              'live_authorization_verified': False})
        return 1
    except KeyboardInterrupt:
        emit({'status': 'setup_stopped', 'live_authorization_verified': False})
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
