"""Source history, blacklist and whitelist.

A source that repeatedly fails is a bad source, not a bad day. The history
records every considered video, how often it was selected and how many clips
it produced, so a poor source can be avoided. The blacklist supports manual
entries and automatic low-quality entries; the whitelist boosts trusted
channels without bypassing the hard eligibility rules.
"""

from datetime import datetime, timezone

SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS discovery_source_history (
        video_id TEXT PRIMARY KEY, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
        times_considered INTEGER NOT NULL DEFAULT 0, times_selected INTEGER NOT NULL DEFAULT 0,
        clips_generated INTEGER NOT NULL DEFAULT 0, performance REAL,
        channel TEXT, title TEXT, outcome TEXT)''',
    '''CREATE TABLE IF NOT EXISTS discovery_blacklist (
        video_id TEXT PRIMARY KEY, reason TEXT NOT NULL, added_at TEXT NOT NULL, automatic INTEGER NOT NULL DEFAULT 0)''',
    '''CREATE TABLE IF NOT EXISTS discovery_whitelist (
        channel_id TEXT PRIMARY KEY, channel TEXT, boost REAL NOT NULL DEFAULT 0.1, added_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS discovery_query_performance (
        query TEXT PRIMARY KEY, results_found INTEGER NOT NULL DEFAULT 0,
        eligible INTEGER NOT NULL DEFAULT 0, selected INTEGER NOT NULL DEFAULT 0,
        clips_generated INTEGER NOT NULL DEFAULT 0, performance REAL, last_used TEXT)''',
]


def _now():
    return datetime.now(timezone.utc).isoformat()


class SourceHistory:
    """Persistent record of considered sources and the operator's trust lists."""

    def __init__(self, database):
        from app.repositories.database import Database
        self.db = database if isinstance(database, Database) else Database(database)
        with self.db.connection(write=True) as db:
            for statement in SCHEMA:
                db.execute(statement)

    def consider(self, video_id, *, channel=None, title=None):
        if not isinstance(video_id, str) or not video_id:
            raise ValueError('A source history entry needs a video identifier')
        with self.db.connection(write=True) as db:
            db.execute('''INSERT INTO discovery_source_history
                (video_id,first_seen,last_seen,times_considered,channel,title)
                VALUES (?,?,?,1,?,?)
                ON CONFLICT(video_id) DO UPDATE SET last_seen=excluded.last_seen,
                times_considered=times_considered+1,
                channel=coalesce(excluded.channel,discovery_source_history.channel),
                title=coalesce(excluded.title,discovery_source_history.title)''',
                       (video_id, _now(), _now(), channel, title))

    def select(self, video_id, clips=0):
        with self.db.connection(write=True) as db:
            db.execute('''UPDATE discovery_source_history SET times_selected=times_selected+1,
                clips_generated=clips_generated+?, outcome='selected' WHERE video_id=?''',
                       (max(0, int(clips)), video_id))

    def blacklist(self, video_id, reason='manual', automatic=False):
        with self.db.connection(write=True) as db:
            db.execute('''INSERT INTO discovery_blacklist (video_id,reason,added_at,automatic)
                VALUES (?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET reason=excluded.reason''',
                       (video_id, str(reason)[:200], _now(), 1 if automatic else 0))

    def blacklist_ids(self):
        with self.db.connection() as db:
            return {row['video_id'] for row in
                    db.execute('SELECT video_id FROM discovery_blacklist').fetchall()}

    def whitelist(self, channel_id, channel=None, boost=0.1):
        with self.db.connection(write=True) as db:
            db.execute('''INSERT INTO discovery_whitelist (channel_id,channel,boost,added_at)
                VALUES (?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET boost=excluded.boost,
                channel=coalesce(excluded.channel,discovery_whitelist.channel)''',
                       (channel_id, channel, float(boost), _now()))

    def whitelist_boosts(self):
        with self.db.connection() as db:
            return {row['channel_id']: row['boost'] for row in
                    db.execute('SELECT channel_id,boost FROM discovery_whitelist').fetchall()}

    def record_query(self, query, *, results=0, eligible=0, selected=0):
        with self.db.connection(write=True) as db:
            db.execute('''INSERT INTO discovery_query_performance
                (query,results_found,eligible,selected,last_used) VALUES (?,?,?,?,?)
                ON CONFLICT(query) DO UPDATE SET results_found=results_found+excluded.results_found,
                eligible=eligible+excluded.eligible, selected=selected+excluded.selected,
                last_used=excluded.last_used''',
                       (str(query)[:300], max(0, int(results)), max(0, int(eligible)),
                        max(0, int(selected)), _now()))

    def query_performance(self):
        with self.db.connection() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM discovery_query_performance ORDER BY selected DESC, eligible DESC').fetchall()]

    def report(self):
        with self.db.connection() as db:
            rows = db.execute('''SELECT video_id,times_considered,times_selected,clips_generated,
                performance,channel,title,outcome FROM discovery_source_history
                ORDER BY times_considered DESC LIMIT 100''').fetchall()
        return [dict(row) for row in rows]
