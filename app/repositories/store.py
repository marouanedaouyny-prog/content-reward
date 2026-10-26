"""Domain data and authoritative order snapshots; JSON is import/export only."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import nullcontext
from pathlib import Path

from app.core.logging import event_record
from app.repositories.database import Database, timestamp


def encode(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True)


def moment_identifier(order_id, source_id, plan):
    key = f"{order_id}:{source_id}:{plan['start_seconds']}:{plan['duration_seconds']}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


class Store(Database):
    def save_order(self, state, *, expected_revision=None, connection=None, sync_candidates=True, duration_ms=None):
        identifier = str(uuid.UUID(state['id']))
        with nullcontext(connection) if connection is not None else self.connection(write=True) as db:
            old = db.execute('SELECT revision FROM orders WHERE id=?', (identifier,)).fetchone()
            if expected_revision is not None and (old is None or old['revision'] != expected_revision):
                raise ValueError('Order changed; reload before saving')
            revision = old['revision'] + 1 if old else 1
            now = timestamp()
            db.execute('''INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,status=excluded.status,
                stage=excluded.stage,config=excluded.config,state=excluded.state,revision=excluded.revision''',
                (identifier, state.get('created_at', now), now, state['status'], state['stage'],
                 encode(state['config']), encode(state), revision))
            record = event_record('order_updated', order_id=identifier, stage=state['stage'], status=state['status'],
                                  duration_ms=duration_ms)
            db.execute('INSERT INTO pipeline_events VALUES (?,?,?,?,?,?,?)',
                (uuid.uuid4().hex, identifier, None, state['stage'], record['event'], now, encode(record)))
            if sync_candidates:
                self._save_reservations(db, state)
        return revision

    def get_order(self, identifier):
        return self.read_order(identifier)[0]

    def read_order(self, identifier):
        with self.connection() as db:
            row = db.execute('SELECT state,revision FROM orders WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError('Order not found')
        return json.loads(row['state']), row['revision']

    def revision(self, identifier):
        with self.connection() as db:
            row = db.execute('SELECT revision FROM orders WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError('Order not found')
        return row['revision']

    def latest_order(self):
        with self.connection() as db:
            row = db.execute('SELECT state FROM orders ORDER BY created_at DESC,rowid DESC LIMIT 1').fetchone()
        return json.loads(row['state']) if row else None

    def list_orders(self, limit=100):
        with self.connection() as db:
            rows = db.execute('SELECT state FROM orders ORDER BY created_at DESC LIMIT ?', (max(1, min(1000, limit)),)).fetchall()
        return [json.loads(row['state']) for row in rows]

    def _save_reservations(self, db, state):
        moments = state.get('moments', [])
        for index, entry in enumerate(state.get('clip_entries', []) + state.get('skipped_entries', [])):
            source = entry.get('source') or state.get('source_selection') or {}
            moment = entry.get('moment') or (moments[index] if index < len(moments) else {})
            plan = entry.get('source_clip_plan') or moment.get('clip_plan')
            if not source.get('id') or not plan:
                continue
            db.execute('''INSERT INTO sources VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,metadata=excluded.metadata''',
                (source['id'], source.get('url'), source.get('title', ''), source.get('duration'),
                 source.get('views', source.get('view_count')), source.get('published_at'), encode(source)))
            identifier = moment_identifier(state['id'], source['id'], plan)
            db.execute('''INSERT INTO candidate_moments VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id)
                DO UPDATE SET excerpt=excluded.excerpt,score=excluded.score,features=excluded.features''',
                (identifier, state['id'], source['id'], plan['start_seconds'], plan['duration_seconds'],
                 moment.get('source_excerpt', ''), moment.get('selection', {}).get('score'), encode(moment)))

    def reservations(self, current_id=None):
        with self.connection() as db:
            rows = db.execute('''SELECT * FROM candidate_moments WHERE order_id != ?''', (current_id or '',)).fetchall()
        return [dict(source_id=row['source_id'], order_id=row['order_id'], source_excerpt=row['excerpt'],
                     clip_plan=dict(start_seconds=row['start_seconds'], duration_seconds=row['duration_seconds'])) for row in rows]

    def import_orders(self, orders, *, lock_factory=None):
        for path in sorted(Path(orders).glob('*/order.json')):
            try:
                identifier = str(uuid.UUID(path.parent.name))
                with self.connection() as db:
                    if db.execute('SELECT 1 FROM orders WHERE id=?', (identifier,)).fetchone():
                        continue
                    if db.execute('SELECT 1 FROM manifest_imports WHERE path=?', (str(path.resolve()),)).fetchone():
                        continue
                with lock_factory(path.parent) if lock_factory else nullcontext():
                    if path.stat().st_size > 32 * 1024 * 1024:
                        raise ValueError('Historical manifest exceeds size limit')
                    from app.repositories.imports import validate_order_snapshot
                    state = validate_order_snapshot(json.loads(path.read_text(encoding='utf-8')), identifier)
                    with self.connection(write=True) as db:
                        if not db.execute('SELECT 1 FROM orders WHERE id=?', (identifier,)).fetchone():
                            self.save_order(state, connection=db)
                        db.execute('INSERT OR IGNORE INTO manifest_imports VALUES (?,?,?)',
                                   (str(path.resolve()), timestamp(), 'imported'))
            except (ValueError, TypeError, KeyError, OSError, sqlite3.IntegrityError, sqlite3.ProgrammingError):
                with self.connection(write=True) as db:
                    db.execute('INSERT OR IGNORE INTO manifest_imports VALUES (?,?,?)',
                               (str(path.resolve()), timestamp(), 'invalid_manifest'))
            except Exception as error:
                if error.__class__.__name__ != 'OrderBusy':
                    raise
                # A running legacy controller owns this snapshot. Retry import later.

    def import_warnings(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM manifest_imports WHERE outcome!='imported'")]

    def save_clip(self, clip):
        with self.connection(write=True) as db:
            db.execute('''INSERT INTO clips VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id)
                DO UPDATE SET path=excluded.path,subtitles=excluded.subtitles,sha256=excluded.sha256,
                status=excluded.status,settings=excluded.settings''',
                (clip['id'], clip['order_id'], clip.get('source_id'), clip.get('moment_id'),
                 clip['path'], clip.get('subtitles'), clip['sha256'], clip.get('caption', ''),
                 clip.get('caption_style', 'studio'), clip.get('framing', 'fit'),
                 clip.get('status', 'READY'), clip.get('created_at', timestamp()), encode(clip.get('settings', {})),))

    def list_clips(self, order_id=None):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM clips WHERE (? IS NULL OR order_id=?) ORDER BY created_at DESC',
                              (order_id, order_id)).fetchall()
        return [dict(row) | {'settings': json.loads(row['settings'])} for row in rows]

    def enqueue_post(self, record, *, settings=None):
        """Persist a local review/schedule item; this method never calls a publisher."""
        from app.core.config import load_settings
        from app.models.domain import PostQueueEntry
        from growth.timing import content_spacing_violations

        settings = settings or load_settings()
        entry = PostQueueEntry.model_validate(record)
        now = datetime.now(timezone.utc)
        status = 'SCHEDULED' if entry.scheduled_at > now else 'READY'
        with self.connection(write=True) as db:
            clip = db.execute('SELECT source_id,settings,status FROM clips WHERE id=?',
                              (entry.clip_id,)).fetchone()
            if clip is None or clip['status'] != 'READY':
                raise ValueError('Only an existing ready clip can enter the review queue')
            clip_settings = json.loads(clip['settings'])
            topic = clip_settings.get('topic') or clip_settings.get('niche')
            existing_rows = db.execute('''SELECT q.scheduled_at,c.source_id,c.settings
                FROM posting_queue q JOIN clips c ON c.id=q.clip_id
                WHERE q.status IN ('READY','SCHEDULED') AND q.platform=? AND q.account_id IS ?''',
                (entry.platform, entry.account_id)).fetchall()
            existing = []
            for row in existing_rows:
                saved_settings = json.loads(row['settings'])
                existing.append({'scheduled_at': row['scheduled_at'], 'source_id': row['source_id'],
                                 'topic': saved_settings.get('topic') or saved_settings.get('niche')})
            candidate = {'scheduled_at': entry.scheduled_at, 'source_id': clip['source_id'], 'topic': topic}
            violations = content_spacing_violations(candidate, existing,
                max_posts_per_day=settings.posting.max_per_day,
                minimum_gap_minutes=settings.posting.minimum_gap_minutes,
                same_source_hours=settings.posting.same_source_hours,
                same_topic_hours=settings.posting.same_topic_hours,
                timezone_name=settings.posting.timezone)
            if violations:
                raise ValueError('Post conflicts with queue spacing rules: ' + ', '.join(violations))
            created = timestamp()
            try:
                db.execute('''INSERT INTO posting_queue
                    (id,clip_id,platform,scheduled_at,caption,hashtags,cta,account_id,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (entry.id, entry.clip_id, entry.platform, entry.scheduled_at.isoformat(), entry.caption,
                     encode(entry.hashtags), entry.cta, entry.account_id, status, created, created))
            except sqlite3.IntegrityError as error:
                raise ValueError('Queue entry already exists or violates a database constraint') from error
        return self.get_post_queue_entry(entry.id)

    def get_post_queue_entry(self, identifier):
        with self.connection() as db:
            row = db.execute('SELECT * FROM posting_queue WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError('Queue entry not found')
        return dict(row) | {'hashtags': json.loads(row['hashtags'])}

    def list_post_queue(self, *, status=None, platform=None, limit=100):
        allowed = {'READY', 'SCHEDULED', 'PUBLISHING', 'PUBLISHED', 'FAILED'}
        if status is not None and status not in allowed:
            raise ValueError('Unknown queue status')
        if platform is not None and platform not in {'youtube', 'instagram', 'tiktok'}:
            raise ValueError('Unknown platform')
        with self.connection() as db:
            rows = db.execute('''SELECT * FROM posting_queue
                WHERE (? IS NULL OR status=?) AND (? IS NULL OR platform=?)
                ORDER BY scheduled_at,id LIMIT ?''',
                (status, status, platform, platform, max(1, min(1000, limit)))).fetchall()
        return [dict(row) | {'hashtags': json.loads(row['hashtags'])} for row in rows]

    def posting_history(self, platform, account_id=None):
        """Return only observations tied to confirmed external publication evidence."""
        with self.connection() as db:
            rows = db.execute('''SELECT m.platform,m.views,m.followers_generated,p.metadata
                FROM performance_metrics m JOIN publications p ON p.clip_id=m.clip_id
                AND p.platform=m.platform WHERE m.platform=? AND p.status='PUBLISHED'
                AND json_extract(p.metadata,'$.account_id') IS ?
                ORDER BY m.collected_at DESC''', (platform, account_id)).fetchall()
        history = []
        for row in rows:
            metadata = json.loads(row['metadata'])
            if (metadata.get('network_attempted') is not True
                    or metadata.get('adapter') not in ('youtube', 'instagram', 'tiktok')):
                continue
            posted_at = metadata.get('published_at')
            if posted_at:
                history.append({'platform': row['platform'], 'posted_at': posted_at,
                                'views': row['views'], 'followers_gained': row['followers_generated']})
        return history

    def get_clip(self, identifier):
        with self.connection() as db:
            row = db.execute('SELECT * FROM clips WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError('Clip not found')
        return dict(row) | {'settings': json.loads(row['settings'])}

    def record_render_event(self, order_id, clip_id, outcome, attempt_id):
        if (outcome not in ('started', 'succeeded', 'failed') or not all(
                isinstance(value, str) and value for value in (order_id, clip_id, attempt_id))):
            raise ValueError('Invalid render attempt event')
        name = 'render_' + outcome
        record = event_record(name, order_id=order_id, clip_id=clip_id, stage='render',
                              attempt_id=attempt_id)
        with self.connection(write=True) as db:
            existing = db.execute("""SELECT 1 FROM pipeline_events WHERE order_id=? AND clip_id=?
                AND json_extract(data,'$.attempt_id')=? AND event=?""",
                (order_id, clip_id, attempt_id, name)).fetchone()
            if existing:
                return
            if outcome != 'started':
                started = db.execute("""SELECT 1 FROM pipeline_events WHERE order_id=? AND clip_id=?
                    AND json_extract(data,'$.attempt_id')=? AND event='render_started'""",
                    (order_id, clip_id, attempt_id)).fetchone()
                if not started:
                    start = event_record('render_started', order_id=order_id, clip_id=clip_id,
                        stage='render', attempt_id=attempt_id)
                    db.execute('INSERT INTO pipeline_events VALUES (?,?,?,?,?,?,?)',
                        (uuid.uuid4().hex, order_id, clip_id, 'render', 'render_started',
                         start['timestamp'], encode(start)))
            db.execute('INSERT INTO pipeline_events VALUES (?,?,?,?,?,?,?)',
                (uuid.uuid4().hex, order_id, clip_id, 'render', name,
                 record['timestamp'], encode(record)))

    def save_campaign(self, campaign):
        data = campaign.model_dump(mode='json')
        with self.connection(write=True) as db:
            db.execute('''INSERT INTO campaigns VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id)
                DO UPDATE SET title=excluded.title,platform=excluded.platform,creator=excluded.creator,
                status=excluded.status,rules=excluded.rules,deadline=excluded.deadline,metadata=excluded.metadata''',
                (campaign.id, campaign.title, campaign.platform, campaign.creator, campaign.status,
                 encode(data['rules']), data['deadline'], encode(data)))
        return campaign

    def get_campaign(self, identifier):
        from campaigns.models import Campaign
        with self.connection() as db:
            row = db.execute('SELECT metadata FROM campaigns WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError('Campaign not found')
        return Campaign.model_validate_json(row['metadata'])

    def list_campaigns(self):
        with self.connection() as db:
            rows = db.execute('SELECT id FROM campaigns ORDER BY title,id').fetchall()
        return [self.get_campaign(row['id']) for row in rows]
