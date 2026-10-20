"""Domain data and authoritative order snapshots; JSON is import/export only."""

import json
import uuid
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
    def save_order(self, state, *, expected_revision=None, connection=None, sync_candidates=True):
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
            record = event_record('order_updated', order_id=identifier, stage=state['stage'], status=state['status'])
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
                    state = json.loads(path.read_text(encoding='utf-8'))
                    if state['id'] != identifier or not isinstance(state['config'], dict):
                        raise ValueError('Historical manifest identity mismatch')
                    with self.connection(write=True) as db:
                        if not db.execute('SELECT 1 FROM orders WHERE id=?', (identifier,)).fetchone():
                            self.save_order(state, connection=db)
                        db.execute('INSERT OR IGNORE INTO manifest_imports VALUES (?,?,?)',
                                   (str(path.resolve()), timestamp(), 'imported'))
            except (ValueError, TypeError, KeyError, OSError):
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

    def get_clip(self, identifier):
        with self.connection() as db:
            row = db.execute('SELECT * FROM clips WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError('Clip not found')
        return dict(row) | {'settings': json.loads(row['settings'])}

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
