"""Bounded, integrity-checked cache for reusable source artifacts."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.repositories.database import Database

MAX_CACHE_BYTES = 16 * 1024 * 1024


def cache_key(kind, identity):
    if not isinstance(kind, str) or not kind or len(kind) > 64:
        raise ValueError('Cache kind must be a short nonempty string')
    try:
        encoded = json.dumps({'kind': kind, 'identity': identity}, sort_keys=True,
                             ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError) as error:
        raise ValueError('Cache identity must be finite JSON data') from error
    return hashlib.sha256(b'content-reward-cache-v1\0' + encoded).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as content:
        for chunk in iter(lambda: content.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class CacheRepository:
    def __init__(self, database):
        self.db = database if isinstance(database, Database) else Database(database)

    @staticmethod
    def _expiry(ttl_seconds):
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 30 * 86400:
            raise ValueError('Cache lifetime must be from one second through 30 days')
        return (_now() + timedelta(seconds=ttl_seconds)).isoformat()

    def get_json(self, kind, identity, *, max_bytes=MAX_CACHE_BYTES):
        key = cache_key(kind, identity)
        with self.db.connection() as db:
            row = db.execute('SELECT payload,expires_at FROM cache_entries WHERE key=?', (key,)).fetchone()
        if row is None:
            return None
        if row['expires_at'] <= _now().isoformat() or len(row['payload'].encode('utf-8')) > max_bytes:
            self._delete(key)
            return None
        try:
            return json.loads(row['payload'])
        except (TypeError, ValueError):
            self._delete(key)
            return None

    def put_json(self, kind, identity, value, *, ttl_seconds, max_bytes=MAX_CACHE_BYTES):
        key = cache_key(kind, identity)
        try:
            payload = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
        except (TypeError, ValueError) as error:
            raise ValueError('Cached payload must be finite JSON data') from error
        if len(payload.encode('utf-8')) > max_bytes:
            raise ValueError('Cached payload exceeds the configured size limit')
        with self.db.connection(write=True) as db:
            db.execute('''INSERT INTO cache_entries VALUES (?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET kind=excluded.kind,payload=excluded.payload,
                created_at=excluded.created_at,expires_at=excluded.expires_at''',
                (key, kind, payload, _now().isoformat(), self._expiry(ttl_seconds)))
        return key

    def get_file(self, kind, identity):
        value = self.get_json(kind, identity)
        if (not isinstance(value, dict) or not {'path', 'sha256', 'size'} <= set(value)
                or set(value) - {'path', 'sha256', 'size', 'identity'}
                or ('identity' in value and value['identity'] != identity)):
            return None
        try:
            path = Path(value['path']).resolve(strict=True)
            if (not path.is_file() or path.stat().st_size != value['size'] or
                    value['size'] > 2 * 1024 * 1024 * 1024 or _digest(path) != value['sha256']):
                self._delete(cache_key(kind, identity))
                return None
            return path
        except (OSError, TypeError, ValueError):
            self._delete(cache_key(kind, identity))
            return None

    def put_file(self, kind, identity, path, *, ttl_seconds):
        path = Path(path).resolve(strict=True)
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024 * 1024:
            raise ValueError('Cached file must be a regular file within the size limit')
        return self.put_json(kind, identity,
            {'path': str(path), 'sha256': _digest(path), 'size': path.stat().st_size,
             'identity': identity},
            ttl_seconds=ttl_seconds)

    def find_file(self, kind, matches):
        """Return the first verified file whose recorded identity matches a predicate."""
        if not callable(matches):
            raise TypeError('matches must be callable')
        with self.db.connection() as db:
            rows = db.execute('SELECT key,payload,expires_at FROM cache_entries WHERE kind=?',
                              (kind,)).fetchall()
        now = _now().isoformat()
        for row in rows:
            if row['expires_at'] <= now:
                continue
            try:
                payload = json.loads(row['payload'])
                identity = payload['identity']
                if not isinstance(identity, dict) or not matches(identity):
                    continue
                if cache_key(kind, identity) != row['key']:
                    continue
                path = self.get_file(kind, identity)
                if path is not None:
                    return path, identity
            except (KeyError, TypeError, ValueError):
                continue
        return None

    def record_access(self, kind, result, *, reused_bytes=None, requested_seconds=None):
        if not isinstance(kind, str) or not kind or len(kind) > 64:
            raise ValueError('Cache kind must be a short nonempty string')
        if result not in {'exact_hit', 'containing_hit', 'miss', 'trim_failed'}:
            raise ValueError('Unknown cache access result')
        if (reused_bytes is not None and (isinstance(reused_bytes, bool) or not isinstance(reused_bytes, int)
                or reused_bytes < 0)):
            raise ValueError('Reused bytes must be a nonnegative integer')
        if (requested_seconds is not None and (isinstance(requested_seconds, bool)
                or not isinstance(requested_seconds, (int, float)) or requested_seconds < 0)):
            raise ValueError('Requested duration must be a nonnegative number')
        with self.db.connection(write=True) as db:
            db.execute('INSERT INTO cache_accesses VALUES (?,?,?,?,?,?)',
                (str(uuid.uuid4()), kind, result, _now().isoformat(), reused_bytes, requested_seconds))

    def stats(self):
        with self.db.connection() as db:
            rows = db.execute('''SELECT kind,result,count(*) AS count,
                coalesce(sum(reused_bytes),0) AS bytes_reused,
                coalesce(sum(requested_seconds),0) AS requested_seconds
                FROM cache_accesses GROUP BY kind,result''').fetchall()
        by_kind = {}
        for row in rows:
            group = by_kind.setdefault(row['kind'], {'exact_hits': 0, 'containing_hits': 0,
                'misses': 0, 'trim_failures': 0, 'bytes_reused': 0, 'requested_seconds': 0.0})
            field = {'exact_hit': 'exact_hits', 'containing_hit': 'containing_hits',
                     'miss': 'misses', 'trim_failed': 'trim_failures'}[row['result']]
            group[field] = row['count']
            group['bytes_reused'] += row['bytes_reused']
            group['requested_seconds'] += row['requested_seconds']
        hits = sum(group['exact_hits'] + group['containing_hits'] for group in by_kind.values())
        misses = sum(group['misses'] + group['trim_failures'] for group in by_kind.values())
        requests = hits + misses
        return {'requests': requests, 'hits': hits, 'misses': misses,
                'hit_rate': round(hits / requests, 6) if requests else None,
                'bytes_reused': sum(group['bytes_reused'] for group in by_kind.values()),
                'requested_seconds': sum(group['requested_seconds'] for group in by_kind.values()),
                'by_kind': by_kind,
                'basis': 'Instrumented cache lookups since telemetry was enabled; historical access is unavailable.'}

    def delete(self, kind, identity):
        self._delete(cache_key(kind, identity))

    def _delete(self, key):
        with self.db.connection(write=True) as db:
            db.execute('DELETE FROM cache_entries WHERE key=?', (key,))
