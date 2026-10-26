"""Explicit SQLite transactions, foreign keys, migrations and consistent backups."""

import sqlite3
from contextlib import closing, contextmanager
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
        UNIQUE(experiment_id,clip_id))''',
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
POSTING_QUEUE_SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS posting_queue (
        id TEXT PRIMARY KEY, clip_id TEXT NOT NULL REFERENCES clips(id), platform TEXT NOT NULL
        CHECK(platform IN ('youtube','instagram','tiktok')), scheduled_at TEXT NOT NULL,
        caption TEXT NOT NULL, hashtags TEXT NOT NULL, cta TEXT NOT NULL,
        account_id TEXT, status TEXT NOT NULL CHECK(status IN ('READY','SCHEDULED','PUBLISHING','PUBLISHED','FAILED')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS idx_posting_queue_status_time ON posting_queue(status,scheduled_at)',
    'CREATE INDEX IF NOT EXISTS idx_posting_queue_clip_platform ON posting_queue(clip_id,platform)',
]
PERFORMANCE_PROFILE_VISITS_MIGRATION = [
    'ALTER TABLE performance_metrics ADD COLUMN profile_visits INTEGER CHECK(profile_visits IS NULL OR profile_visits>=0)',
]
EXPERIMENT_REPLICATES_MIGRATION = [
    '''CREATE TABLE experiment_variants_v5 (
        id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id),
        clip_id TEXT NOT NULL REFERENCES clips(id), variant TEXT NOT NULL, settings TEXT NOT NULL,
        UNIQUE(experiment_id,clip_id))''',
    'INSERT INTO experiment_variants_v5 SELECT * FROM experiment_variants',
    'DROP TABLE experiment_variants',
    'ALTER TABLE experiment_variants_v5 RENAME TO experiment_variants',
]
CACHE_ACCESS_TELEMETRY_MIGRATION = [
    '''CREATE TABLE cache_accesses (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL,
        result TEXT NOT NULL CHECK(result IN ('exact_hit','containing_hit','miss','trim_failed')),
        occurred_at TEXT NOT NULL, reused_bytes INTEGER CHECK(reused_bytes IS NULL OR reused_bytes>=0),
        requested_seconds REAL CHECK(requested_seconds IS NULL OR requested_seconds>=0))''',
    'CREATE INDEX idx_cache_access_kind_time ON cache_accesses(kind,occurred_at)',
]
OBSERVED_HASHTAGS_MIGRATION = [
    'ALTER TABLE performance_metrics ADD COLUMN hashtags TEXT',
]
OBSERVED_CTA_MIGRATION = [
    'ALTER TABLE performance_metrics ADD COLUMN cta_used TEXT',
]
MEASUREMENT_CONTEXT_MIGRATION = [
    'ALTER TABLE performance_metrics ADD COLUMN measurement_context TEXT',
    '''ALTER TABLE performance_metrics ADD COLUMN average_view_percentage REAL
       CHECK(average_view_percentage IS NULL OR average_view_percentage>=0)''',
    '''ALTER TABLE performance_metrics ADD COLUMN audience_watch_ratio REAL
       CHECK(audience_watch_ratio IS NULL OR audience_watch_ratio>=0)''',
]
EXPERIMENT_SCOPE_MIGRATION = [
    '''ALTER TABLE experiments ADD COLUMN scope TEXT NOT NULL DEFAULT 'single_moment'
       CHECK(scope IN ('single_moment','content_blocks'))''',
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
        migrations = (SCHEMA, INDEXES, POSTING_QUEUE_SCHEMA, PERFORMANCE_PROFILE_VISITS_MIGRATION,
                      EXPERIMENT_REPLICATES_MIGRATION, CACHE_ACCESS_TELEMETRY_MIGRATION,
                      OBSERVED_HASHTAGS_MIGRATION, OBSERVED_CTA_MIGRATION, MEASUREMENT_CONTEXT_MIGRATION,
                      EXPERIMENT_SCOPE_MIGRATION)
        if existed and version < len(migrations):
            self.backup(self.path.with_suffix(self.path.suffix + f'.before-v{version + 1}.bak'))
        with self.connection(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            for number, statements in enumerate(migrations, 1):
                if db.execute('SELECT 1 FROM schema_migrations WHERE version=?', (number,)).fetchone():
                    continue
                for statement in statements:
                    if number == 4 and 'profile_visits' in {
                            row['name'] for row in db.execute('PRAGMA table_info(performance_metrics)')}:
                        continue
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
        with self.connection() as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
            target.commit()
        return destination
