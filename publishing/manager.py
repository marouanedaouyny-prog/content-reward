"""Eligibility and content-bound idempotency surround every adapter invocation."""

import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path

from app.core.errors import PipelineError
from app.repositories.database import timestamp
from app.repositories.store import encode
from campaigns.validation import validate_campaign
from clipping.media import file_hash
from publishing.manual import ManualExportPublisher


class PublishingManager:
    def __init__(self, store, *, output, publisher=None):
        self.store = store
        self.publisher = publisher or ManualExportPublisher(output)

    def publish(self, clip_id, metadata, *, campaign_id, platform, key):
        if self.publisher.mode not in ('manual', 'mock'):
            raise PipelineError('PUBLISH_ERROR', stage='publish', retryable=False)
        if (not isinstance(key, str) or not 1 <= len(key) <= 300 or not isinstance(metadata, dict)
                or set(metadata) - {'caption', 'title'} or not isinstance(metadata.get('caption'), str)
                or len(metadata['caption']) > 10000):
            raise ValueError('Invalid publication metadata or idempotency key')
        clip = self.store.get_clip(clip_id)
        path = Path(clip['path'])
        if not path.is_file() or file_hash(path) != clip['sha256']:
            raise ValueError('Clip changed or is missing; review a new export')
        if clip['status'] != 'READY':
            raise ValueError('Clip is not ready for review/export')
        campaign = self.store.get_campaign(campaign_id)
        settings = clip['settings']
        eligible = validate_campaign(campaign, dict(source_id=clip['source_id'],
            duration_seconds=settings.get('source_clip_plan', {}).get('duration_seconds'),
            transcript=settings.get('transcript', '')), metadata, platform,
            source=settings.get('source'), for_publication=True)
        if not eligible.eligible:
            raise ValueError('Publication campaign validation failed: ' + ', '.join(eligible.violations))
        request = dict(clip_id=clip_id, sha256=clip['sha256'], campaign_id=campaign_id,
                       platform=platform, metadata=metadata, adapter=self.publisher.mode)
        fingerprint = hashlib.sha256(encode(request).encode()).hexdigest()
        with self.store.connection(write=True) as db:
            old = db.execute('SELECT * FROM publications WHERE idempotency_key=?', (key,)).fetchone()
            if old:
                if old['payload_hash'] != fingerprint:
                    raise ValueError('Idempotency key belongs to different publication inputs')
                if old['status'] == 'READY':
                    return dict(old) | {'metadata': json.loads(old['metadata'])}
                identifier = old['id']
                db.execute("UPDATE publications SET status='PUBLISHING',updated_at=? WHERE id=?",
                           (timestamp(), identifier))
            else:
                identifier = str(uuid.uuid4())
                now = timestamp()
                db.execute('INSERT INTO publications VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (identifier, clip_id, platform, 'PUBLISHING', key, fingerprint, None, None,
                     now, now, encode(request), None))
        try:
            outcome = self.publisher.publish(clip, {**metadata, 'platform': platform, 'publication_id': identifier})
            if outcome.status != 'READY' or outcome.url is not None or outcome.external_id is not None:
                raise PipelineError('PUBLISH_ERROR', stage='publish', retryable=False)
            saved = {**request, 'eligibility': eligible.model_dump(), 'adapter_result': asdict(outcome)}
            with self.store.connection(write=True) as db:
                db.execute("UPDATE publications SET status='READY',metadata=?,error_code=NULL,updated_at=? WHERE id=?",
                           (encode(saved), timestamp(), identifier))
        except Exception:
            with self.store.connection(write=True) as db:
                db.execute("UPDATE publications SET status='PUBLISH_FAILED',error_code='PUBLISH_ERROR',updated_at=? WHERE id=?",
                           (timestamp(), identifier))
            raise PipelineError('PUBLISH_ERROR', stage='publish', retryable=False) from None
        with self.store.connection() as db:
            row = db.execute('SELECT * FROM publications WHERE id=?', (identifier,)).fetchone()
        return dict(row) | {'metadata': json.loads(row['metadata'])}
