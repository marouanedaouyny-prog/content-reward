"""Persistent source research, using observed popularity rather than viral forecasts."""

import json
import math
import os
import re
import subprocess
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from clipping import media

NICHES = (
    {'name': 'Gaming', 'query': 'gaming streamer full interview'},
    {'name': 'AI & technology', 'query': 'AI technology interview demonstration'},
    {'name': 'Business', 'query': 'entrepreneur business podcast interview'},
    {'name': 'Fitness', 'query': 'fitness training coach interview'},
    {'name': 'Sport', 'query': 'football sports full interview'},
    {'name': 'Culture & comedy', 'query': 'comedy culture podcast interview'},
)
INTERVAL = 6 * 3600
MIN_SOURCE_SECONDS = 1200
MAX_SOURCE_SECONDS = 7200
RANKING_NOTE = ('Search-derived popularity signals, not a viral prediction. Views/hour since upload '
    'is a lifetime average, not measured recent growth. Missing dates or counts remain unknown. '
    'Campaign permissions and the actual transcript must be reviewed before posting.')


class DiscoveryUnavailable(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def youtube_api(resource, params):
    # Fixed host, verified TLS, inherited proxy, and no API key in returned errors or reports.
    url = 'https://www.googleapis.com/youtube/v3/' + resource + '?' + urlencode(
        {**params, 'key': os.environ['YOUTUBE_API_KEY']})
    try:
        with urlopen(url, timeout=20) as response:
            content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError('YouTube research response is too large')
        return json.loads(content)
    except HTTPError as exc:
        if exc.code == 429 or exc.code >= 500:
            raise DiscoveryUnavailable('YouTube search temporarily unavailable or rate limited') from exc
        raise ValueError(f'YouTube API refused the search (HTTP {exc.code}). Check key, API access and quota.') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DiscoveryUnavailable('Research connection unavailable. Check network access.') from exc


def iso_duration(value):
    match = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', value or '')
    return sum(float(number or 0) * unit for number, unit in zip(match.groups(), (3600, 60, 1))) if match else None


def discover(niche):
    if discovery_provider() == 'selenium_browser':
        interpreter = os.environ.get('CLIPPING_SELENIUM_PYTHON')
        if not interpreter:
            raise ValueError('Selenium Python is not configured. Use start-youtube-clipping.ps1 -Selenium.')
        try:
            result = json.loads(media.command([interpreter, str(Path(__file__).with_name('youtube_browser.py')),
                '--query', niche['query']], timeout=180, kill_tree=True))
        except subprocess.TimeoutExpired as exc:
            raise DiscoveryUnavailable('Chrome search timed out. Saved research will retry.') from exc
        except ValueError as exc:
            raise ValueError('Selenium search could not start. Check its Python installation.') from exc
        if not isinstance(result, dict):
            raise ValueError('Selenium search returned invalid metadata')
        if result.get('status') == 'source_unavailable':
            raise DiscoveryUnavailable('Chrome could not load YouTube. Check browser access in your normal terminal.')
        if result.get('status') != 'ok' or not isinstance(result.get('entries'), list):
            raise ValueError('Chrome driver or browser unavailable. Use the Selenium launcher in your normal terminal.')
        return [item for item in result['entries'][:8] if isinstance(item, dict)]
    if os.environ.get('YOUTUBE_API_KEY'):
        found = youtube_api('search', {'part': 'id', 'type': 'video', 'q': niche['query'],
            'publishedAfter': (now() - timedelta(days=14)).isoformat(), 'order': 'viewCount',
            'maxResults': 8, 'regionCode': os.environ.get('TREND_REGION', 'US'),
            'relevanceLanguage': os.environ.get('TREND_LANGUAGE', 'en'), 'videoDuration': 'long'})
        identifiers = [item.get('id', {}).get('videoId') for item in found.get('items', [])]
        identifiers = [item for item in identifiers if re.fullmatch(r'[\w-]{11}', item or '')]
        if not identifiers:
            return []
        records = youtube_api('videos', {'part': 'snippet,statistics,contentDetails', 'id': ','.join(identifiers)})
        results = []
        for item in records.get('items', []):
            snippet = item.get('snippet', {})
            results.append({'id': item.get('id'), 'title': snippet.get('title'),
                'uploader': snippet.get('channelTitle'), 'published_at': snippet.get('publishedAt'),
                'view_count': finite_number(item.get('statistics', {}).get('viewCount')),
                'duration': iso_duration(item.get('contentDetails', {}).get('duration')),
                'live_status': 'not_live' if snippet.get('liveBroadcastContent') == 'none' else 'is_live'})
        return results
    try:
        found = json.loads(media.command([*media.ytdlp_command(), '--ignore-config', '--skip-download',
            '--flat-playlist', '--dump-single-json', '--no-warnings', '--socket-timeout', '8',
            '--retries', '1', '--extractor-retries', '1', 'ytsearch8:' + niche['query']],
            timeout=30, kill_tree=True))
        entries = [item for item in (found.get('entries') or [])[:8] if isinstance(item, dict)]
        # Flat search often omits dates. Inspect every bounded long-video candidate,
        # skipping known short sources before spending another network request.
        for index, item in enumerate(entries):
            duration = finite_number(item.get('duration'))
            if duration is not None and not MIN_SOURCE_SECONDS < duration <= MAX_SOURCE_SECONDS:
                continue
            identifier = item.get('id')
            if ((not item.get('timestamp') and not item.get('upload_date')
                    or duration is None or finite_number(item.get('view_count')) is None)
                    and isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier)):
                try:
                    details = json.loads(media.command([*media.ytdlp_command(), '--ignore-config', '--skip-download',
                        '--dump-single-json', '--no-playlist', '--no-warnings', '--socket-timeout', '8',
                        '--retries', '1', '--extractor-retries', '1',
                        'https://www.youtube.com/watch?v=' + identifier], timeout=30, kill_tree=True))
                except (ValueError, subprocess.TimeoutExpired):
                    continue  # An unavailable upload must not discard the other findings.
                entries[index] = {**item, **details}
        return entries
    except json.JSONDecodeError as exc:
        raise ValueError('Public video search returned invalid metadata. Check the yt-dlp installation.') from exc
    except subprocess.TimeoutExpired as exc:
        raise DiscoveryUnavailable('Public video search timed out. Saved research will retry.') from exc
    except ValueError as exc:
        transient = any(term in str(exc).lower() for term in (
            'unable to connect to proxy', 'connection refused', '10061', 'timed out',
            'temporary failure', 'connection reset', 'name resolution', 'getaddrinfo failed',
            'http error 500', 'http error 502', 'http error 503', 'http error 504', 'http error 429'))
        if transient:
            raise DiscoveryUnavailable('Public video search connection unavailable. Saved research will retry.') from exc
        raise ValueError('Public video search failed. Check the installed yt-dlp version and search command.') from exc


def finite_number(value):
    try:
        number = float(value)
        return number if not isinstance(value, bool) and math.isfinite(number) and number >= 0 else None
    except (ValueError, TypeError):
        return None


def discovery_provider():
    if os.environ.get('CLIPPING_DISCOVERY_PROVIDER') == 'selenium':
        return 'selenium_browser'
    return 'youtube_api' if os.environ.get('YOUTUBE_API_KEY') else 'public_search'


def candidate(item, niche):
    identifier = item.get('id')
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier):
        return None
    if item.get('is_live') or item.get('live_status') in ('is_live', 'is_upcoming', 'post_live'):
        return None
    published = None
    try:
        if item.get('published_at'):
            published = datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
            if published.tzinfo is None:
                published = None
        elif item.get('timestamp') is not None:
            published = datetime.fromtimestamp(float(item['timestamp']), timezone.utc)
        elif item.get('upload_date'):
            published = datetime.strptime(item['upload_date'], '%Y%m%d').replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        pass
    if published and not now() - timedelta(days=14) <= published <= now():
        return None
    views, duration = finite_number(item.get('view_count')), finite_number(item.get('duration'))
    age = max((now() - published).total_seconds() / 3600, 1) if published else None
    return {'id': identifier, 'url': 'https://www.youtube.com/watch?v=' + identifier,
        'title': str(item.get('title') or 'Untitled video')[:300],
        'creator': str(item.get('uploader') or item.get('channel') or 'Unknown creator')[:200],
        'niches': [niche['name']], 'views': int(views) if views is not None else None,
        'published_at': published.isoformat() if published else None, 'observed_at': now().isoformat(),
        'duration': duration, 'views_per_hour_since_upload': round(views / age, 2) if views is not None and age else None,
        'measured_growth_per_hour': None, 'eligible_preview': bool(published and views is not None
            and duration is not None and MIN_SOURCE_SECONDS < duration <= MAX_SOURCE_SECONDS)}


class TrendResearchAgent:
    def __init__(self, engine, niches=None):
        self.engine = engine
        self.niches = tuple(niches) if niches is not None else NICHES
        with engine.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS clipping_trend_run (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, output TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, next_attempt_at TEXT)''')

    def setting(self, key):
        with self.engine.connection() as db:
            row = db.execute('SELECT value FROM clipping_setting WHERE key=?', (key,)).fetchone()
        return row['value'] if row else None

    def enabled(self):
        return self.setting('trends_enabled') != 'false'

    def set_enabled(self, enabled):
        with self.engine.connection() as db:
            db.execute('INSERT OR REPLACE INTO clipping_setting VALUES (?,?)', ('trends_enabled', str(enabled).lower()))
        return self.status()

    def get(self, run_id):
        with self.engine.connection() as db:
            row = db.execute('SELECT * FROM clipping_trend_run WHERE id=?', (run_id,)).fetchone()
        if not row:
            raise KeyError('Research run not found')
        value = dict(row)
        data = json.loads(value.pop('output'))
        return {**value, **data}

    def status(self):
        with self.engine.connection() as db:
            row = db.execute('SELECT id FROM clipping_trend_run ORDER BY created_at DESC, rowid DESC LIMIT 1').fetchone()
        return {'enabled': self.enabled(), 'paused': self.engine.killed(),
            'interval_hours': INTERVAL // 3600, 'next_scan_at': self.setting('trends_next_scan'),
            'latest': self.get(row['id']) if row else None, 'niches': [item['name'] for item in self.niches],
            'provider': discovery_provider()}

    def request_scan(self, auto_preview=False):
        with self.engine.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            provider = discovery_provider()
            db.execute("""UPDATE clipping_trend_run SET status='expired',updated_at=?
                WHERE status IN ('queued','retry_scheduled')
                AND COALESCE(json_extract(output,'$.provider'),'public_search')<>?""", (now().isoformat(), provider))
            row = db.execute("""SELECT id,created_at,status FROM clipping_trend_run
                WHERE status IN ('queued','running','retry_scheduled')
                AND COALESCE(json_extract(output,'$.provider'),'public_search')=? LIMIT 1""", (provider,)).fetchone()
            if row and row['status'] != 'running' and now() - datetime.fromisoformat(row['created_at']) > timedelta(days=1):
                db.execute("UPDATE clipping_trend_run SET status='expired',updated_at=? WHERE id=?",
                           (now().isoformat(), row['id']))
                row = None
            if row:
                if auto_preview:
                    saved = self.get(row['id'])
                    saved['auto_preview'] = True
                    data = {key: value for key, value in saved.items() if key not in
                            ('id', 'status', 'created_at', 'updated_at', 'next_attempt_at')}
                    # An explicit retry does not have to wait for the background backoff.
                    db.execute("UPDATE clipping_trend_run SET output=?, status=CASE WHEN status='retry_scheduled' THEN 'queued' ELSE status END, next_attempt_at=NULL WHERE id=?",
                               (json.dumps(data), row['id']))
                db.commit()
                return self.get(row['id'])
            identifier = str(uuid.uuid4())
            data = {'results': [], 'failures': [], 'searched_niches': [], 'ranking_note': RANKING_NOTE,
                'provider': discovery_provider(),
                'region': os.environ.get('TREND_REGION', 'US'), 'language': os.environ.get('TREND_LANGUAGE', 'en'),
                'failed_attempts': 0, 'auto_preview': auto_preview}
            db.execute('INSERT INTO clipping_trend_run VALUES (?,?,?,?,?,NULL)',
                (identifier, 'queued', json.dumps(data), now().isoformat(), now().isoformat()))
            db.commit()
        return self.get(identifier)

    def _save(self, run, status, due=None):
        data = {key: value for key, value in run.items() if key not in
                ('id', 'status', 'created_at', 'updated_at', 'next_attempt_at', 'output')}
        with self.engine.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            saved = db.execute('SELECT output FROM clipping_trend_run WHERE id=?', (run['id'],)).fetchone()
            # A user can request the clip while a search is already running.
            if saved and json.loads(saved['output']).get('auto_preview'):
                data['auto_preview'] = True
                run['auto_preview'] = True
            db.execute('UPDATE clipping_trend_run SET status=?,output=?,updated_at=?,next_attempt_at=? WHERE id=?',
                (status, json.dumps(data), now().isoformat(), due, run['id']))
            db.commit()

    def consume_once(self):
        if not self.enabled() or self.engine.killed() or self.engine.shutdown_requested:
            return False
        # Recover a crash between saving a completed scan and creating its one clip.
        with self.engine.connection() as db:
            pending = db.execute("""SELECT id FROM clipping_trend_run WHERE status IN ('completed','partial')
                AND json_extract(output,'$.auto_preview')=1
                AND json_extract(output,'$.preview_job_id') IS NULL
                AND json_extract(output,'$.preview_error') IS NULL ORDER BY created_at LIMIT 1""").fetchone()
        if pending:
            self._queue_preview(self.get(pending['id']))
            return True
        with self.engine.connection() as db:
            db.execute("UPDATE clipping_trend_run SET status='queued' WHERE status='running' AND updated_at<?",
                ((now() - timedelta(minutes=10)).isoformat(),))
            busy = db.execute("SELECT id FROM clipping_trend_run WHERE status IN ('queued','running','retry_scheduled') LIMIT 1").fetchone()
        if not busy and (not self.setting('trends_next_scan') or self.setting('trends_next_scan') <= now().isoformat()):
            self.request_scan()
        with self.engine.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("""SELECT id FROM clipping_trend_run WHERE status='queued'
                OR (status='retry_scheduled' AND next_attempt_at<=?) ORDER BY created_at LIMIT 1""", (now().isoformat(),)).fetchone()
            if not row:
                db.commit()
                return False
            db.execute("UPDATE clipping_trend_run SET status='running',updated_at=? WHERE id=?", (now().isoformat(), row['id']))
            db.commit()
        run = self.get(row['id'])
        transient = False
        run['failures'] = []
        should_stop = lambda: not self.enabled() or self.engine.killed() or self.engine.shutdown_requested
        try:
            with media.processing_control(should_stop):
                for niche in self.niches:
                    if should_stop():
                        raise media.ProcessingInterrupted()
                    if niche['name'] in run['searched_niches']:
                        continue
                    try:
                        records = discover(niche)
                        existing = {item['id']: item for item in run['results']}
                        for record in records[:8]:
                            item = candidate(record, niche)
                            if item:
                                if item['id'] in existing:
                                    item['niches'] = list(dict.fromkeys(existing[item['id']]['niches'] + item['niches']))
                                existing[item['id']] = item
                        run['results'] = list(existing.values())
                        run['searched_niches'].append(niche['name'])
                    except (DiscoveryUnavailable, ValueError) as exc:
                        transient = transient or isinstance(exc, DiscoveryUnavailable)
                        run['failures'].append({'niche': niche['name'], 'message': str(exc)})
                    self._save(run, 'running')
        except media.ProcessingInterrupted:
            self._save(run, 'queued')
            return True
        self._rank(run)
        if transient:
            run['failed_attempts'] += 1
            from app.core.errors import retry_delay
            delay = retry_delay(run['failed_attempts'], maximum_attempts=self.engine.settings.worker.maximum_attempts,
                                base=300)
            self._save(run, 'retry_scheduled' if delay is not None else 'failed',
                       (now() + timedelta(seconds=delay)).isoformat() if delay is not None else None)
            if delay is None:
                with self.engine.connection() as db:
                    db.execute('INSERT OR REPLACE INTO clipping_setting VALUES (?,?)',
                               ('trends_next_scan', (now() + timedelta(seconds=INTERVAL)).isoformat()))
        else:
            self._save(run, 'partial' if run['failures'] and run['results'] else 'failed' if run['failures'] else 'completed')
            if run.get('auto_preview') and (run['results'] or not run['failures']):
                self._queue_preview(self.get(run['id']))
            with self.engine.connection() as db:
                db.execute('INSERT OR REPLACE INTO clipping_setting VALUES (?,?)',
                    ('trends_next_scan', (now() + timedelta(seconds=INTERVAL)).isoformat()))
        return True

    def _queue_preview(self, run):
        try:
            run['preview_job_id'] = self.preview(run['id'])['id']
        except ValueError as exc:
            run['preview_error'] = str(exc)
        self._save(run, run['status'], run.get('next_attempt_at'))
        if run['status'] in ('completed', 'partial'):
            with self.engine.connection() as db:
                db.execute('INSERT OR REPLACE INTO clipping_setting VALUES (?,?)',
                           ('trends_next_scan', (now() + timedelta(seconds=INTERVAL)).isoformat()))

    def _rank(self, run):
        with self.engine.connection() as db:
            previous = db.execute("SELECT output FROM clipping_trend_run WHERE id<>? AND status IN ('completed','partial') ORDER BY created_at DESC LIMIT 1", (run['id'],)).fetchone()
        old = json.loads(previous['output']) if previous else {}
        same_context = all(old.get(key) == run.get(key) for key in ('provider', 'region', 'language'))
        baseline = {item['id']: item for item in old.get('results', [])} if same_context else {}
        for item in run['results']:
            prior = baseline.get(item['id'])
            if prior and prior['views'] is not None and item['views'] is not None:
                hours = (datetime.fromisoformat(item['observed_at']) - datetime.fromisoformat(prior['observed_at'])).total_seconds() / 3600
                if hours >= .25 and item['views'] >= prior['views']:
                    item['measured_growth_per_hour'] = round((item['views'] - prior['views']) / hours, 2)
        run['results'].sort(key=lambda item: (item['measured_growth_per_hour'] is not None,
            item['measured_growth_per_hour'] or 0, item['views_per_hour_since_upload'] or 0,
            item['views'] or 0), reverse=True)

    def preview(self, run_id, candidate_id=None, *, caption_style=None, target_duration=30,
                framing_mode=None):
        run = self.get(run_id)
        if now() - datetime.fromisoformat(run['created_at']) > timedelta(days=1):
            raise ValueError('Refresh research before preparing a preview from an old scan')
        choices = [item for item in run['results'] if item['eligible_preview']
                   and MIN_SOURCE_SECONDS < (item.get('duration') or 0) <= MAX_SOURCE_SECONDS and
                   (candidate_id is None or item['id'] == candidate_id)]
        if not choices:
            raise ValueError('No eligible recorded source with known recent dates, views and duration. Refresh research.')
        source = choices[0]
        data = {'campaign': {'title': 'Research preview: ' + source['title'][:160], 'url': source['url'],
            'platform': 'youtube', 'experience': 'current', 'rules': 'Private subtitled source preview. No publishing or submission.',
            'rights_notes': 'Research source only. Campaign and reposting authorization are not recorded.',
            'duration_min': 5, 'duration_max': 60}, 'source_url': source['url'], 'dry_run': False,
            'preview_only': True, 'auto_clip': True, 'language': run['language'],
            'research_keywords': ', '.join(source['niches'])[:200], 'caption': source['title'],
            'clip_plan': {'start_seconds': 0, 'duration_seconds': target_duration, 'aspect_ratio': '9:16'},
            'source_selection': {**source, 'checked_on': source['observed_at'][:10],
                'method': 'Recent niche search ranked by observed popularity proxies; not a viral forecast.',
                'research_run_id': run_id}}
        if caption_style is not None:
            data['caption_style'] = caption_style
            data['campaign']['duration_min'] = 15
        if framing_mode is not None:
            data['framing_mode'] = framing_mode
        return self.engine.create(data, 'trend-preview:' + run_id + ':' + source['id'])
