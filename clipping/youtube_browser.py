"""Public YouTube browser metadata; run with the Python that has Selenium installed."""

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import getproxies


def search_ids(data):
    stack, identifiers = [data], []
    for _ in range(10000):
        if not stack or len(identifiers) == 8:
            break
        value = stack.pop()
        if isinstance(value, dict):
            record = value.get('videoRenderer')
            if isinstance(record, dict):
                identifier = record.get('videoId')
                length_node = record.get('lengthText')
                length = length_node.get('simpleText', '') if isinstance(length_node, dict) else ''
                if isinstance(length, str) and re.fullmatch(r'\d+(?::\d{2}){1,2}', length):
                    duration = 0
                    for part in length.split(':'):
                        duration = duration * 60 + int(part)
                    if not 1200 < duration <= 7200:
                        continue
                if isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier):
                    if identifier not in identifiers:
                        identifiers.append(identifier)
            stack.extend(reversed(list(value.values())))
        elif isinstance(value, list):
            stack.extend(reversed(value))
    return identifiers


def dom_ids(links):
    identifiers = []
    for value in links[:60]:
        if not isinstance(value, str):
            continue
        parsed = urlparse(value)
        values = parse_qs(parsed.query).get('v', [])
        if (parsed.scheme != 'https' or parsed.hostname not in ('youtube.com', 'www.youtube.com')
                or parsed.path != '/watch' or len(values) != 1):
            continue
        identifier = values[0]
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier) and identifier not in identifiers:
            identifiers.append(identifier)
        if len(identifiers) == 8:
            break
    return identifiers


def exact_number(value):
    if isinstance(value, str) and re.fullmatch(r'\d{1,18}', value):
        return int(value)
    return None


def watch_record(player, identifier):
    details = player.get('videoDetails', {}) if isinstance(player, dict) else {}
    if not isinstance(details, dict) or details.get('videoId') != identifier:
        return None
    record = {'id': identifier, 'title': str(details.get('title') or 'Untitled video')[:300],
              'uploader': str(details.get('author') or '')[:200],
              'view_count': exact_number(details.get('viewCount')),
              'duration': exact_number(details.get('lengthSeconds')),
              'live_status': 'is_live' if details.get('isLive') else 'not_live'}
    microformat = player.get('microformat')
    micro = microformat.get('playerMicroformatRenderer') if isinstance(microformat, dict) else None
    micro = micro if isinstance(micro, dict) else {}
    date = micro.get('publishDate') or micro.get('uploadDate')
    if isinstance(date, str):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            record['upload_date'] = date.replace('-', '')
        else:
            try:
                published = datetime.fromisoformat(date.replace('Z', '+00:00'))
                if published.tzinfo:
                    record['published_at'] = published.isoformat()
            except ValueError:
                pass
    return record


def proxy_capabilities(proxies):
    addresses = {}
    for name in ('http', 'https'):
        value = proxies.get(name) or proxies.get('all') or proxies.get('http') or proxies.get('https')
        if not value:
            continue
        parsed = urlparse(value if '://' in value else 'http://' + value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Unsupported browser proxy configuration; use the normal-terminal launcher.')
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        host = '[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname
        addresses['httpProxy' if name == 'http' else 'sslProxy'] = f'{host}:{port}'
    return {'proxyType': 'manual', **addresses} if addresses else None


class BrowserSetupError(Exception):
    def __init__(self, reason):
        self.reason = reason


def browser_failure_reason(error):
    messages, seen = [], set()
    for _ in range(8):
        if error is None or id(error) in seen:
            break
        seen.add(id(error))
        messages.append(type(error).__name__.lower() + ': ' + str(error).lower())
        error = error.__cause__ or error.__context__
    text = ' '.join(messages)
    if any(value in text for value in ('access is denied', 'permission denied', 'winerror 5')):
        return 'browser_execution_refused'
    if any(value in text for value in ('error sending request', 'connection refused',
            'unable to connect to proxy', 'timed out', 'name resolution', 'getaddrinfo failed')):
        return 'browser_connection_unavailable'
    if 'session not created' in text or 'sessionnotcreatedexception' in text:
        return 'browser_session_not_created'
    return 'driver_or_browser_unavailable'


@contextmanager
def browser_session():
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.proxy import Proxy
    except ImportError as exc:
        raise BrowserSetupError('selenium_unavailable') from exc
    root = Path(__file__).resolve().parents[1] / '.workflow-tests'
    profiles = (root / 'selenium-profiles').resolve()
    profiles.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix='youtube-', dir=profiles)).resolve()
    driver = None
    try:
        os.environ['SE_CACHE_PATH'] = str(root / 'selenium-cache')
        os.environ['SE_TIMEOUT'] = '15'
        os.environ['SE_AVOID_STATS'] = 'true'
        os.environ['SE_AVOID_BROWSER_DOWNLOAD'] = 'true'
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--user-data-dir=' + str(profile))
        options.add_argument('--lang=en-US')
        options.page_load_strategy = 'eager'
        # The browser and Selenium Manager must preserve inherited network policy.
        # Never clear proxies or use the user's logged-in browser profile.
        try:
            caps = proxy_capabilities(getproxies())
        except ValueError as exc:
            raise BrowserSetupError('proxy_configuration_unavailable') from exc
        if caps:
            options.proxy = Proxy(caps)
        try:
            driver = webdriver.Chrome(options=options, service=Service(log_output=subprocess.DEVNULL))
            driver.set_page_load_timeout(20)
        except Exception as exc:
            raise BrowserSetupError(browser_failure_reason(exc)) from exc
        yield driver
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if profile.resolve().is_relative_to(profiles):
            shutil.rmtree(profile, ignore_errors=True)


def search(driver, query):
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.support.ui import WebDriverWait
    driver.get('https://www.youtube.com/results?' + urlencode({'search_query': query, 'hl': 'en', 'gl': 'US'}))
    data = WebDriverWait(driver, 20).until(lambda browser: browser.execute_script('return window.ytInitialData || null;'))
    identifiers = search_ids(data)
    if not identifiers:
        links = driver.execute_script('return Array.from(document.querySelectorAll("a[href*=\'/watch?v=\']"), a => a.href).slice(0,60);')
        identifiers = dom_ids(links) if isinstance(links, list) else []
    records = []
    for identifier in identifiers:
        try:
            driver.get('https://www.youtube.com/watch?v=' + identifier + '&hl=en')
            # Read only the needed public fields; omit stream URLs, cookies and formats.
            player = WebDriverWait(driver, 15).until(lambda browser: browser.execute_script(
                'const p=window.ytInitialPlayerResponse; return p && p.videoDetails ? '
                '{videoDetails:p.videoDetails,microformat:p.microformat} : null;'))
        except WebDriverException:
            continue
        record = watch_record(player, identifier)
        if record:
            records.append(record)
    if identifiers and not records:
        raise ValueError('The source video pages could not be inspected')
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description='Search public YouTube videos with an isolated Selenium browser.')
    parser.add_argument('--query')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    if not args.check and (not args.query or len(args.query) > 300):
        parser.error('Provide --query with up to 300 characters, or --check')
    logging.getLogger('selenium').setLevel(logging.CRITICAL)
    try:
        with browser_session() as driver:
            if args.check:
                driver.get('https://www.youtube.com/?hl=en')
                if 'youtube' not in driver.title.lower():
                    raise ValueError('YouTube did not load')
                result = {'status': 'ok', 'browser_started': True, 'youtube_reachable': True}
            else:
                result = {'status': 'ok', 'entries': search(driver, args.query)}
    except BrowserSetupError as exc:
        result = {'status': 'source_unavailable' if exc.reason == 'browser_connection_unavailable'
                  else 'setup_blocked', 'reason': exc.reason}
    except PermissionError:
        result = {'status': 'setup_blocked', 'reason': 'browser_execution_refused'}
    except OSError:
        result = {'status': 'setup_blocked', 'reason': 'browser_runtime_unavailable'}
    except Exception:
        result = {'status': 'source_unavailable', 'reason': 'youtube_page_unavailable'}
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
