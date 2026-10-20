"""Explicit SQLite transactions, foreign keys, migrations and consistent backups."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        status TEXT NOT NULL, stage TEXT NOT NULL, config TEXT NOT NULL,
        state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1)''',
    '''CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY, url TEXT, title TEXT NOT NULL, duration REAL,
        views INTEGER, published_at TEXT, metadata TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS candidate_moments (
        id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
        source_id TEXT NOT NULL REFERENCES sources(id), start_seconds REAL NOT NULL,
        duration_seconds REAL NOT NULL CHECK(duration_seconds>0), excerpt TEXT NOT NULL,
        score REAL, features TEXT NOT NULL, UNIQUE(order_id,source_id,start_seconds,duration_seconds))''',
    '''CREATE TABLE IF NOT EXISTS clips (
        id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
        source_id TEXT REFERENCES sources(id), moment_id TEXT REFERENCES candidate_moments(id),
        path TEXT NOT NULL, subtitles TEXT, sha256 TEXT NOT NULL, caption TEXT NOT NULL,
        caption_style TEXT NOT NULL, framing TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL, settings TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS campaigns (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, platform TEXT NOT NULL,
        creator TEXT, status TEXT NOT NULL, rules TEXT NOT NULL,
        deadline TEXT, metadata TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS publications (
        id TEXT PRIMARY KEY, clip_id TEXT NOT NULL REFERENCES clips(id), platform TEXT NOT NULL,
        status TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL,
        external_id TEXT, url TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        metadata TEXT NOT NULL, error_code TEXT)''',
    '''CREATE TABLE IF NOT EXISTS performance_metrics (
        id TEXT PRIMARY KEY, clip_id TEXT NOT NULL REFERENCES clips(id), platform TEXT NOT NULL,
        collected_at TEXT NOT NULL, views INTEGER, likes INTEGER, comments INTEGER,
        shares INTEGER, saves INTEGER, average_watch_time REAL, completion_rate REAL,
        retention REAL, followers_generated INTEGER, campaign_accepted INTEGER,
        campaign_rejected INTEGER, rejection_reason TEXT, reward_amount TEXT,
        provenance TEXT NOT NULL, UNIQUE(clip_id,platform,collected_at))''',
    '''CREATE TABLE IF NOT EXISTS rewards (
        id TEXT PRIMARY KEY, clip_id TEXT NOT NULL REFERENCES clips(id),
        campaign_id TEXT REFERENCES campaigns(id), status TEXT NOT NULL,
        amount TEXT, currency TEXT NOT NULL, reference TEXT NOT NULL UNIQUE,
        recorded_at TEXT NOT NULL, provenance TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS pipeline_events (
        id TEXT PRIMARY KEY, order_id TEXT, clip_id TEXT, stage TEXT,
        event TEXT NOT NULL, timestamp TEXT NOT NULL, data TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS experiments (
        id TEXT PRIMARY KEY, source_moment_id TEXT NOT NULL REFERENCES candidate_moments(id),
        name TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS experiment_variants (
        id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id),
        clip_id TEXT NOT NULL REFERENCES clips(id), variant TEXT NOT NULL, settings TEXT NOT NULL,
        UNIQUE(experiment_id,variant), UNIQUE(experiment_id,clip_id))''',
    '''CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY, order_id TEXT REFERENCES orders(id), clip_id TEXT REFERENCES clips(id),
        stage TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, metadata TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS cache_entries (
        key TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS manifest_imports (
        path TEXT PRIMARY KEY, imported_at TEXT NOT NULL, outcome TEXT NOT NULL)''',
]
INDEXES = [
    'CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC)',
    'CREATE INDEX IF NOT EXISTS idx_clips_order ON clips(order_id)',
    'CREATE INDEX IF NOT EXISTS idx_moments_source ON candidate_moments(source_id,start_seconds)',
    'CREATE INDEX IF NOT EXISTS idx_metrics_clip_time ON performance_metrics(clip_id,collected_at DESC)',
    'CREATE INDEX IF NOT EXISTS idx_events_order_time ON pipeline_events(order_id,timestamp)',
]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.is_file()
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            current = db.execute("SELECT name FROM sqlite_master WHERE name='schema_migrations'").fetchone()
            version = db.execute('SELECT coalesce(max(version),0) FROM schema_migrations').fetchone()[0] if current else 0
        if existed and version < 2:
            self.backup(self.path.with_suffix(self.path.suffix + f'.before-v{version + 1}.bak'))
        with self.connection(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            for number, statements in enumerate((SCHEMA, INDEXES), 1):
                if db.execute('SELECT 1 FROM schema_migrations WHERE version=?', (number,)).fetchone():
                    continue
                for statement in statements:
                    db.execute(statement)
                db.execute('INSERT INTO schema_migrations VALUES (?,?)', (number, timestamp()))

    @contextmanager
    def connection(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=30000')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def backup(self, destination):
        destination = Path(destination).resolve()
        if destination == self.path:
            raise ValueError('Backup must use a separate destination')
        if destination.exists():
            return destination  # Preserve the original pre-migration snapshot.
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as source, sqlite3.connect(destination) as target:
            source.backup(target)
        return destination
