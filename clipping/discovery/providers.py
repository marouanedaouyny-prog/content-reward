"""Discovery providers.

Every provider only searches and returns broad results. Filtering, ranking and
tier relaxation belong to the eligibility engine, never to a provider adapter.
No provider is mandatory: the engine falls back through the chain and reports
every failure with a structured error code.

Discovery never downloads media. Only metadata, and the public captions the
clip pipeline fetches later, are allowed here.
"""

import json
import os
import re
import subprocess
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from clipping.discovery.models import (SourceCandidate, finite_number, now, parse_datetime)

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


class ProviderError(Exception):
    """A provider failure with a stable machine-readable code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class DiscoveryProvider:
    """The provider contract: search broadly, return candidates, never filter."""

    name = 'base'

    def search(self, query, limit):
        raise NotImplementedError

    def lookup(self, video_id):
        """Optional light metadata lookup for a candidate with missing fields."""
        return None

    def available(self):
        return True

    @staticmethod
    def _candidate(item, provider):
        identifier = item.get('id')
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier):
            return None
        live = bool(item.get('is_live')) or item.get('live_status') in ('is_live', 'is_upcoming', 'post_live')
        published = (parse_datetime(item.get('published_at')) or parse_datetime(item.get('timestamp'))
                     or parse_datetime(item.get('upload_date')))
        duration = finite_number(item.get('duration'))
        views = finite_number(item.get('view_count', item.get('views')))
        title = str(item.get('title') or 'Untitled video')[:300]
        channel = item.get('uploader') or item.get('channel')
        return SourceCandidate(
            id=identifier, title=title,
            url='https://www.youtube.com/watch?v=' + identifier,
            duration_seconds=int(duration) if duration is not None else None,
            views=int(views) if views is not None else None,
            upload_date=published, channel=str(channel)[:200] if channel else None,
            provider=provider, channel_id=item.get('channel_id'),
            description=(str(item.get('description'))[:600] if item.get('description') else None),
            is_live=live)


class YtDlpProvider(DiscoveryProvider):
    """Zero-cost search through the installed yt-dlp, without downloading media."""

    name = 'yt_dlp'

    def __init__(self, timeout=30, enrich=True, minimum_duration=None, maximum_duration=None):
        self.timeout = timeout
        self.enrich = enrich
        self.minimum_duration = minimum_duration
        self.maximum_duration = maximum_duration

    def _command(self, extra, timeout=None):
        from clipping import media
        return media.command([*media.ytdlp_command(), '--ignore-config', '--skip-download',
                              '--no-warnings', '--socket-timeout', '8', '--retries', '1',
                              '--extractor-retries', '1', *extra],
                             timeout=timeout or self.timeout, kill_tree=True)

    def search_records(self, query, limit):
        """Return the raw provider records for one query."""
        if not isinstance(query, str) or not query.strip():
            raise ProviderError('INVALID_QUERY', 'A discovery query must be a nonempty string')
        try:
            payload = self._command(['--flat-playlist', '--dump-single-json',
                                     f'ytsearch{max(1, int(limit))}:{query}'])
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ProviderError('PROVIDER_INVALID_METADATA',
                                'The public search provider returned invalid metadata') from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError('PROVIDER_TIMEOUT', 'The public search provider timed out') from exc
        except ValueError as exc:
            raise ProviderError('PROVIDER_FAILED', 'The public search provider failed') from exc
        entries = data.get('entries') if isinstance(data, dict) else None
        return [item for item in (entries or []) if isinstance(item, dict)][:max(1, int(limit))]

    def search(self, query, limit):
        records = self.search_records(query, limit)
        if self.enrich:
            records = self._enrich(records)
        return [candidate for candidate in
                (self._candidate(item, self.name) for item in records) if candidate]

    def _enrich(self, records):
        """Look up publication data for candidates whose flat search record is incomplete."""
        enriched = []
        for index, item in enumerate(records):
            duration = finite_number(item.get('duration'))
            if duration is not None and self.minimum_duration is not None and duration < self.minimum_duration:
                continue
            if duration is not None and self.maximum_duration is not None and duration > self.maximum_duration:
                continue
            identifier = item.get('id')
            complete = (item.get('timestamp') or item.get('upload_date') or item.get('published_at'))
            if ((complete and duration is not None and finite_number(item.get('view_count')) is not None)
                    or not isinstance(identifier, str)):
                enriched.append(item)
                continue
            details = self.lookup(identifier)
            if details:
                enriched.append({**item, **details})
            else:
                enriched.append(item)
        return enriched

    def lookup(self, video_id):
        if not isinstance(video_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            return None
        try:
            payload = self._command(['--dump-single-json', '--no-playlist',
                                     'https://www.youtube.com/watch?v=' + video_id], timeout=self.timeout)
            data = json.loads(payload)
        except (ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None


class YouTubeApiProvider(DiscoveryProvider):
    """The official search API, used only when a key is configured."""

    name = 'youtube_api'

    def __init__(self, api, region='US', language='en', max_age_days=None, long_only=False,
                 timeout=20):
        self.api = api
        self.region = region
        self.language = language
        self.max_age_days = max_age_days
        self.long_only = long_only
        self.timeout = timeout

    def available(self):
        return bool(os.environ.get('YOUTUBE_API_KEY'))

    def _call(self, resource, params):
        try:
            return self.api(resource, params)
        except Exception as exc:  # noqa: BLE001 - provider failures are reported, never hidden.
            code = getattr(exc, 'code', None)
            raise ProviderError(code or 'PROVIDER_FAILED', 'The YouTube search API request failed') from exc

    def search_records(self, query, limit):
        params = {'part': 'id', 'type': 'video', 'q': query, 'order': 'viewCount',
                  'maxResults': max(1, min(50, int(limit))), 'regionCode': self.region,
                  'relevanceLanguage': self.language}
        if self.max_age_days:
            params['publishedAfter'] = (now() - timedelta(days=self.max_age_days)).isoformat()
        if self.long_only:
            params['videoDuration'] = 'long'
        found = self._call('search', params)
        identifiers = [item.get('id', {}).get('videoId') for item in (found.get('items') or [])
                       if isinstance(item, dict)]
        identifiers = [item for item in identifiers if isinstance(item, str)
                       and re.fullmatch(r'[\w-]{11}', item)]
        if not identifiers:
            return []
        records = self._call('videos', {'part': 'snippet,statistics,contentDetails',
                                        'id': ','.join(identifiers)})
        results = []
        for item in (records.get('items') or []):
            if not isinstance(item, dict):
                continue
            snippet = item.get('snippet') or {}
            statistics = item.get('statistics') or {}
            details = item.get('contentDetails') or {}
            results.append({
                'id': item.get('id'), 'title': snippet.get('title'),
                'uploader': snippet.get('channelTitle'), 'channel_id': snippet.get('channelId'),
                'published_at': snippet.get('publishedAt'),
                'view_count': statistics.get('viewCount'),
                'like_count': statistics.get('likeCount'),
                'comment_count': statistics.get('commentCount'),
                'description': snippet.get('description'),
                'duration': iso_duration(details.get('duration')),
                'live_status': 'not_live' if snippet.get('liveBroadcastContent') == 'none' else 'is_live'})
        return results

    def search(self, query, limit):
        return [candidate for candidate in
                (self._candidate(item, self.name) for item in self.search_records(query, limit))
                if candidate]


class SeleniumProvider(DiscoveryProvider):
    """Fallback-only browser search. Chrome is never required for discovery."""

    name = 'selenium'

    def __init__(self, interpreter=None, timeout=180):
        self.interpreter = interpreter
        self.timeout = timeout

    def _interpreter(self):
        if self.interpreter:
            return self.interpreter
        return os.environ.get('CLIPPING_SELENIUM_PYTHON')

    def available(self):
        return bool(self._interpreter())

    def search_records(self, query, limit):
        from clipping import media
        interpreter = self._interpreter()
        if not interpreter:
            raise ProviderError('CHROME_NOT_FOUND',
                                'No Selenium-capable Python is configured for browser discovery')
        try:
            payload = media.command([interpreter, str(Path(__file__).resolve().parents[1]
                                                     / 'clipping' / 'youtube_browser.py'),
                                     '--query', query], timeout=self.timeout, kill_tree=True)
            data = json.loads(payload)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError('PAGE_LOAD_TIMEOUT', 'The browser search timed out') from exc
        except json.JSONDecodeError as exc:
            raise ProviderError('SEARCH_LAYOUT_CHANGED',
                                'The browser search returned unreadable results') from exc
        except ValueError as exc:
            raise ProviderError('DRIVER_START_FAILED', 'The browser search could not start') from exc
        if not isinstance(data, dict):
            raise ProviderError('SEARCH_LAYOUT_CHANGED', 'The browser search returned invalid metadata')
        status = data.get('status')
        if status == 'source_unavailable':
            raise ProviderError('BROWSER_START_FAILED', 'The browser could not reach YouTube')
        if status != 'ok':
            raise ProviderError(data.get('reason') or 'DRIVER_START_FAILED',
                                'The browser search could not start')
        entries = data.get('entries')
        if not isinstance(entries, list):
            raise ProviderError('SEARCH_LAYOUT_CHANGED', 'The browser search returned invalid results')
        return [item for item in entries if isinstance(item, dict)][:max(1, int(limit))]

    def search(self, query, limit):
        return [candidate for candidate in
                (self._candidate(item, self.name) for item in self.search_records(query, limit))
                if candidate]


class PublicSearchProvider(DiscoveryProvider):
    """Last-resort public search page reader. No key, no browser, no download."""

    name = 'public_search'

    VIDEO = re.compile(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"')
    TITLE = re.compile(r'"title"\s*:\s*\{(?:"runs"\s*:\s*\[\{"text"\s*:\s*"(.*?)"|"simpleText"\s*:\s*"(.*?)")')
    LENGTH = re.compile(r'"lengthText"\s*:\s*\{\s*"simpleText"\s*:\s*"(\d+(?::\d{2}){1,2})"')
    VIEWS = re.compile(r'"viewCountText"\s*:\s*\{\s*"simpleText"\s*:\s*"([\d,\.KM]+)')

    def __init__(self, timeout=20, region='US', language='en'):
        self.timeout = timeout
        self.region = region
        self.language = language

    def _text(self, value):
        return value.replace('\\"', '"').replace('\\u0026', '&').replace('\\n', ' ').strip()

    def _duration(self, value):
        parts = value.split(':')
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return seconds

    def _views(self, value):
        text = value.replace(',', '')
        multiplier = {'K': 1000, 'M': 1000000, 'B': 1000000000}.get(text[-1:].upper(), 1)
        try:
            return int(float(text[:-1] if multiplier != 1 else text) * multiplier)
        except ValueError:
            return None

    def search_records(self, query, limit):
        url = 'https://www.youtube.com/results?' + urlencode(
            {'search_query': query, 'hl': self.language, 'gl': self.region})
        request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Language': 'en-US,en;q=0.9'})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read(3_000_001).decode('utf-8', 'replace')
        except HTTPError as exc:
            raise ProviderError('PROVIDER_FAILED', 'The public search page refused the request') from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError('PROVIDER_UNAVAILABLE',
                                'The public search page is unreachable') from exc
        if len(body) > 3_000_000:
            raise ProviderError('PROVIDER_INVALID_METADATA', 'The public search page response is too large')
        records, seen = [], set()
        for match in self.VIDEO.finditer(body):
            identifier = match.group(1)
            if identifier in seen:
                continue
            seen.add(identifier)
            window = body[match.start():match.start() + 3000]
            title_match = self.TITLE.search(window)
            title = self._text((title_match.group(1) or title_match.group(2)) if title_match else '')
            length_match = self.LENGTH.search(window)
            views_match = self.VIEWS.search(window)
            records.append({
                'id': identifier, 'title': title or 'Untitled video',
                'duration': self._duration(length_match.group(1)) if length_match else None,
                'view_count': self._views(views_match.group(1)) if views_match else None})
            if len(records) >= max(1, int(limit)):
                break
        return records

    def search(self, query, limit):
        return [candidate for candidate in
                (self._candidate(item, self.name) for item in self.search_records(query, limit))
                if candidate]


def iso_duration(value):
    match = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', value or '')
    if not match:
        return None
    return sum(float(number or 0) * unit for number, unit in zip(match.groups(), (3600, 60, 1)))


PROVIDER_ORDER = ('youtube_api', 'yt_dlp', 'selenium', 'public_search')
