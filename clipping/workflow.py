"""Durable, local clipping jobs. Every operation uses its own SQLite connection."""

import hashlib
import json
import math
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

from clipping.template import CAPTION_STYLES, DEFAULT_CAPTION_STYLE, DEFAULT_FRAMING_MODE


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def https_url(value):
    if not isinstance(value, str):
        raise ValueError('URL must be text')
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use a complete HTTPS URL without credentials')
    return value


def aware_time(value):
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError) as exc:
        raise ValueError('Use an ISO timestamp with a timezone') from exc
    if date.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    if date > datetime.now(timezone.utc) + timedelta(minutes=2):
        raise ValueError('Confirmation timestamp cannot be in the future')
    return date.astimezone(timezone.utc)


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError('Job payload must be an object')
    data = json.loads(json.dumps(data, allow_nan=False))
    campaign = data.get('campaign', {})
    if not isinstance(campaign, dict):
        raise ValueError('Campaign must be an object')
    for field in ('title', 'url', 'rights_notes', 'rules'):
        if not isinstance(campaign.get(field), str) or not campaign[field].strip():
            raise ValueError(f'Campaign {field} is required')
    https_url(campaign['url'])
    if campaign.get('platform') not in ('youtube', 'tiktok', 'instagram'):
        raise ValueError('Choose youtube, tiktok, or instagram')
    if campaign.get('experience', 'current') not in ('current', 'legacy'):
        raise ValueError('Choose the current or legacy campaign experience')
    if not isinstance(data.get('dry_run', False), bool):
        raise ValueError('dry_run must be a boolean')
    if not isinstance(data.get('preview_only', False), bool):
        raise ValueError('preview_only must be a boolean')
    if data.get('preview_only') and data.get('dry_run'):
        raise ValueError('Disable DRY_RUN to test the actual video; automatic previews never substitute practice footage')
    if not data.get('preview_only'):
        data.pop('preview_only', None)
    if not isinstance(data.get('auto_clip', False), bool):
        raise ValueError('auto_clip must be a boolean')
    if not isinstance(data.get('research_keywords', ''), str) or len(data.get('research_keywords', '')) > 200:
        raise ValueError('Research keywords must be text, at most 200 characters')
    # Empty new controls have the same meaning as old requests that omit them.
    # Keep their normalized input hash compatible with saved manual jobs.
    if not data.get('auto_clip'):
        data.pop('auto_clip', None)
    if not data.get('research_keywords'):
        data.pop('research_keywords', None)
    hint = data.get('transcription_hint')
    if hint is not None and (not isinstance(hint, str) or len(hint) > 1024):
        raise ValueError('Transcription hint must be text, at most 1024 characters')
    if not hint:
        data.pop('transcription_hint', None)
    if 'source_reference' in data:
        reference = data['source_reference']
        if not isinstance(reference, list) or not 1 <= len(reference) <= 200:
            raise ValueError('Source speech reference must contain one to 200 bounded cues')
        from clipping.media import validate_segments
        validate_segments(reference, 66)
    if not data.get('dry_run') and bool(data.get('source_url')) == bool(data.get('source_path')):
        raise ValueError('Provide exactly one source_url or uploaded source_path')
    if data.get('source_url'):
        https_url(data['source_url'])
    for key in ('source_path', 'transcript_srt', 'language'):
        if data.get(key) is not None and not isinstance(data[key], str):
            raise ValueError(f'{key} must be text')
    plan = data.setdefault('clip_plan', {})
    if not isinstance(plan, dict):
        raise ValueError('clip_plan must be an object')
    plan.setdefault('start_seconds', 0)
    plan.setdefault('duration_seconds', 30)
    plan.setdefault('aspect_ratio', '9:16')
    for key in ('start_seconds', 'duration_seconds'):
        value = plan[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f'{key} must be a finite number')
    if plan['start_seconds'] < 0 or not 1 <= plan['duration_seconds'] <= 180:
        raise ValueError('Clip start must be nonnegative and duration between 1 and 180 seconds')
    if plan['aspect_ratio'] not in ('9:16', '16:9', '1:1'):
        raise ValueError('Choose a supported aspect ratio')
    for key in ('duration_min', 'duration_max'):
        value = campaign.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value < 0):
            raise ValueError(f'Campaign {key} must be a nonnegative number')
    if plan['duration_seconds'] < (campaign.get('duration_min') or 0):
        raise ValueError('Clip is shorter than the campaign minimum')
    if campaign.get('duration_max') is not None and plan['duration_seconds'] > campaign['duration_max']:
        raise ValueError('Clip exceeds the campaign maximum')
    if not isinstance(campaign.get('pre_post_review', False), bool):
        raise ValueError('pre_post_review must be a boolean')
    rate = campaign.get('rate_per_1000')
    if rate is not None and (isinstance(rate, bool) or not isinstance(rate, (int, float))
                             or not math.isfinite(rate) or rate < 0):
        raise ValueError('Reward rate must be a nonnegative finite number')
    if not isinstance(data.get('caption', ''), str):
        raise ValueError('Caption must be text')
    if data.get('caption_style', DEFAULT_CAPTION_STYLE) not in CAPTION_STYLES:
        raise ValueError('Choose classic, colorized, pro, or studio caption style')
    if data.get('framing_mode', DEFAULT_FRAMING_MODE) not in ('crop', 'fit'):
        raise ValueError('Choose crop or fit framing')
    data.setdefault('dry_run', False)
    return data


class ClippingWorkflow:
    WAITING = {'awaiting_campaign_approval': 'campaign_review',
               'awaiting_clip_approval': 'clip_review'}

    def __init__(self, database, storage):
        self.database = Path(database).resolve()
        self.storage = Path(storage).resolve()
        self.active_job = None
        self.shutdown_requested = False
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.storage.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS clipping_job (
                id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                input_hash TEXT NOT NULL, payload TEXT NOT NULL, output TEXT NOT NULL,
                status TEXT NOT NULL, current_step TEXT NOT NULL, error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
            db.execute('CREATE TABLE IF NOT EXISTS clipping_setting (key TEXT PRIMARY KEY, value TEXT)')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def create(self, data, idempotency_key=None):
        if not isinstance(data, dict):
            raise ValueError('Job payload must be an object')
        if os.environ.get('DRY_RUN', '').lower() in ('true', '1', 'yes'):
            data = {**data, 'dry_run': True}
        data = validate_request(data)
        if data.get('source_path'):
            self.safe_path(data['source_path'])
        fingerprint = digest(data)
        key = idempotency_key or fingerprint
        if not isinstance(key, str) or not key or len(key) > 512:
            raise ValueError('Idempotency key must contain between 1 and 512 characters')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM clipping_job WHERE idempotency_key=?', (key,)).fetchone()
            if existing:
                if existing['input_hash'] != fingerprint:
                    raise ValueError('Idempotency key already belongs to different input')
                db.commit()
                return self.get(existing['id'])
            job_id = str(uuid.uuid4())
            now = utcnow()
            preview = data.get('preview_only')
            output = {'source_selection': data['source_selection']} if preview and data.get('source_selection') else {}
            db.execute('INSERT INTO clipping_job VALUES (?,?,?,?,?,?,?,?,?,?)', (
                job_id, key, fingerprint, json.dumps(data), json.dumps(output),
                'queued' if preview else 'awaiting_campaign_approval',
                'source_ingest' if preview else 'campaign_review', None, now, now))
            db.commit()
        return self.get(job_id)

    def create_automatic_preview(self):
        from clipping.automation import ishowspeed_preview
        job = self.create(ishowspeed_preview())
        return self.retry(job['id']) if job['status'] in ('failed', 'blocked') else job

    def get(self, job_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM clipping_job WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise KeyError('Job not found')
        job = dict(row)
        job['payload'] = json.loads(job['payload'])
        job['output'] = json.loads(job['output'])
        job['waiting_step'] = self.WAITING.get(job['status'])
        job['approval_fingerprint'] = (job['output'].get('clip_sha256')
                                       if job['waiting_step'] == 'clip_review' else job['input_hash'])
        return job

    def list(self, limit=50):
        with self.connection() as db:
            rows = db.execute('SELECT id FROM clipping_job ORDER BY created_at DESC LIMIT ?',
                              (max(1, min(limit, 100)),)).fetchall()
        return [self.get(row['id']) for row in rows]

    def safe_path(self, relative):
        path = (self.storage / relative).resolve()
        if not path.is_relative_to(self.storage) or path == self.storage:
            raise ValueError('Artifact must be inside workflow storage')
        return path

    def artifact(self, job_id, kind):
        key = {'clip': 'clip_path', 'subtitles': 'subtitle_path', 'package': 'package_path',
               'transcript': 'transcript_path', 'ideas': 'ideas_path'}.get(kind)
        if not key:
            raise ValueError('Unknown artifact type')
        relative = self.get(job_id)['output'].get(key)
        if not relative:
            raise KeyError('Artifact not ready')
        return self.safe_path(relative)

    def _save(self, job_id, output, status, step, expected='running', error=None):
        with self.connection() as db:
            cursor = db.execute('''UPDATE clipping_job SET output=?, status=?, current_step=?,
                error=?, updated_at=? WHERE id=? AND status=?''',
                (json.dumps(output), status, step, error, utcnow(), job_id, expected))
        if cursor.rowcount != 1:
            raise ValueError('Job state changed; refresh before continuing')

    def approve(self, job_id, step, fingerprint, approved, approver='local operator',
                brand_draft_reference=None):
        job = self.get(job_id)
        if job['waiting_step'] != step or step is None:
            raise ValueError('Approval does not match the waiting step')
        if fingerprint != job['approval_fingerprint']:
            raise ValueError('Approval fingerprint is stale')
        if step == 'clip_review' and approved:
            from clipping.media import file_hash
            if file_hash(self.artifact(job_id, 'clip')) != fingerprint:
                raise ValueError('Clip changed after rendering; approval refused')
            if job['payload']['campaign'].get('pre_post_review') and not job['payload']['dry_run']:
                if not brand_draft_reference or not brand_draft_reference.strip():
                    raise ValueError('Record the brand draft approval reference before proceeding')
        output = job['output']
        output.setdefault('approvals', {})[step] = {
            'approved': approved, 'fingerprint': fingerprint, 'approver': approver,
            'at': utcnow(), 'brand_draft_reference': brand_draft_reference}
        self._save(job_id, output, 'queued' if approved else 'cancelled', step, job['status'])
        return self.get(job_id)

    def killed(self):
        if os.environ.get('KILL_SWITCH', '').lower() in ('true', '1', 'yes'):
            return True
        with self.connection() as db:
            row = db.execute("SELECT value FROM clipping_setting WHERE key='kill_switch'").fetchone()
        return bool(row and row['value'] == 'true')

    def set_kill_switch(self, enabled):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO clipping_setting VALUES ('kill_switch', ?)",
                       ('true' if enabled else 'false',))

    def cancel(self, job_id):
        job = self.get(job_id)
        if job['status'] == 'completed':
            raise ValueError('Completed jobs cannot be cancelled')
        self._save(job_id, job['output'], 'cancelled', job['current_step'], job['status'])
        return self.get(job_id)

    def retry(self, job_id):
        job = self.get(job_id)
        if job['status'] not in ('failed', 'blocked'):
            raise ValueError('Only failed or blocked jobs can be retried')
        if 'automation_retry' in job['output']:
            job['output']['automation_retry'] = {'failed_attempts': 0, 'next_attempt_at': None,
                                                'maximum_attempts': None}
        self._save(job_id, job['output'], 'queued', job['current_step'], job['status'])
        return self.get(job_id)

    def provide_transcript(self, job_id, srt):
        from clipping.media import parse_srt, validate_segments
        job = self.get(job_id)
        if job['status'] != 'awaiting_transcript':
            raise ValueError('Job is not waiting for a transcript')
        validate_segments(parse_srt(srt), job['output']['source_duration'])
        job['payload']['transcript_srt'] = srt
        with self.connection() as db:
            cursor = db.execute("""UPDATE clipping_job SET payload=?, status='queued',
                error=NULL, updated_at=? WHERE id=? AND status='awaiting_transcript'""",
                (json.dumps(job['payload']), utcnow(), job_id))
        if cursor.rowcount != 1:
            raise ValueError('Job state changed; refresh before continuing')
        return self.get(job_id)

    def record_publication(self, job_id, post_url, public_confirmed, published_at):
        from clipping.media import file_hash
        job = self.get(job_id)
        if job['status'] != 'awaiting_publication':
            raise ValueError('Job is not waiting for publication')
        if self.killed():
            raise ValueError('Kill switch enabled')
        if not public_confirmed:
            raise ValueError('Confirm the post is public and processing has finished')
        https_url(post_url)
        parsed = urlparse(post_url)
        platform = job['payload']['campaign']['platform']
        domains = {'youtube': ('youtube.com', 'www.youtube.com', 'youtu.be'),
                   'tiktok': ('tiktok.com', 'www.tiktok.com'),
                   'instagram': ('instagram.com', 'www.instagram.com')}
        post_paths = {'youtube': ('/shorts/', '/watch', '/embed/'),
                      'tiktok': ('/video/',), 'instagram': ('/reel/', '/p/')}
        valid_path = (bool(parsed.path.strip('/')) if parsed.hostname == 'youtu.be'
                      else any(part in parsed.path for part in post_paths[platform]))
        if parsed.hostname not in domains[platform] or not valid_path:
            raise ValueError('Post URL must belong to the selected platform and identify a post')
        approval = job['output']['approvals']['clip_review']
        if file_hash(self.artifact(job_id, 'clip')) != approval['fingerprint']:
            raise ValueError('Approved clip changed; publication confirmation refused')
        published = aware_time(published_at)
        output = job['output']
        output['publication'] = {'url': post_url, 'platform': platform,
                                  'published_at': published.isoformat(), 'status': 'operator_confirmed'}
        if job['payload']['campaign'].get('experience', 'current') == 'current':
            output['submission_deadline'] = (published + timedelta(minutes=30)).isoformat()
        self._save(job_id, output, 'awaiting_submission', 'submission', job['status'])
        return self.get(job_id)

    def record_submission(self, job_id, reference, submitted_at):
        job = self.get(job_id)
        if job['status'] != 'awaiting_submission':
            raise ValueError('Job is not waiting for submission')
        if self.killed():
            raise ValueError('Kill switch enabled')
        if not isinstance(reference, str) or len(reference.strip()) < 3:
            raise ValueError('Record the actual Content Rewards submission confirmation reference')
        submitted = aware_time(submitted_at)
        published = aware_time(job['output']['publication']['published_at'])
        if submitted < published:
            raise ValueError('Submission cannot precede publication')
        output = job['output']
        deadline = output.get('submission_deadline')
        output['submission'] = {'reference': reference.strip(), 'submitted_at': submitted.isoformat(),
                                'status': 'operator_confirmed', 'brand_status': 'pending_review',
                                'within_deadline': submitted <= datetime.fromisoformat(deadline) if deadline else None}
        self._save(job_id, output, 'completed', 'submission_recorded', job['status'])
        return self.get(job_id)

    def record_reward(self, job_id, status, reference, amount=None):
        job = self.get(job_id)
        if job['status'] != 'completed' or 'submission' not in job['output']:
            raise ValueError('Record a real submission before updating its reward')
        if status not in ('pending_review', 'approved', 'rejected', 'flagged', 'paid'):
            raise ValueError('Unknown reward status')
        if not isinstance(reference, str) or len(reference.strip()) < 3:
            raise ValueError('A platform decision or payment reference is required')
        if amount is not None and (status != 'paid' or isinstance(amount, bool)
                                  or not isinstance(amount, (int, float))
                                  or not math.isfinite(amount) or amount < 0):
            raise ValueError('Only confirmed payments accept a nonnegative finite amount')
        if status == 'paid' and amount is None:
            raise ValueError('Record the amount actually received')
        # Append against the latest saved output under a write transaction so
        # concurrent confirmations cannot overwrite one another's receipts.
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status, output FROM clipping_job WHERE id=?', (job_id,)).fetchone()
            output = json.loads(row['output'])
            if row['status'] != 'completed' or 'submission' not in output:
                raise ValueError('Job state changed; refresh before continuing')
            output.setdefault('reward_history', []).append({'status': status, 'reference': reference.strip(),
                                                           'amount': amount, 'recorded_at': utcnow(),
                                                           'source': 'operator_confirmation'})
            db.execute('UPDATE clipping_job SET output=?, updated_at=? WHERE id=?',
                       (json.dumps(output), utcnow(), job_id))
            db.commit()
        return self.get(job_id)

    def heartbeat(self):
        if self.active_job:
            with self.connection() as db:
                db.execute("UPDATE clipping_job SET updated_at=? WHERE id=? AND status='running'",
                           (utcnow(), self.active_job))

    def recover_interrupted(self):
        # Active workers heartbeat; reclaim only abandoned processing leases.
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with self.connection() as db:
            db.execute("UPDATE clipping_job SET status='queued', updated_at=? WHERE status='running' AND updated_at<?",
                       (utcnow(), cutoff))

    def consume_once(self):
        if self.killed() or self.shutdown_requested:
            return False
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("""SELECT id, output FROM clipping_job WHERE status='queued'
                OR (status='retry_scheduled' AND json_extract(output,
                    '$.automation_retry.next_attempt_at') <= ?)
                ORDER BY created_at LIMIT 1""", (utcnow(),)).fetchone()
            if not row:
                db.commit()
                return False
            job_id = row['id']
            output = json.loads(row['output'])
            if 'automation_retry' in output:
                output['automation_retry']['next_attempt_at'] = None
            db.execute("UPDATE clipping_job SET status='running', output=?, error=NULL, updated_at=? WHERE id=?",
                       (json.dumps(output), utcnow(), job_id))
            db.commit()
        job = self.get(job_id)
        self.active_job = job_id
        try:
            from clipping.media import processing_control
            with processing_control(lambda: self.shutdown_requested or self.killed()
                                    or self.get(job_id)['status'] != 'running'):
                self._prepare(job)
        except Exception as exc:
            from clipping.media import (
                ProcessingInterrupted,
                SourceAccessRequired,
                SourceUnavailable,
            )
            current = self.get(job_id)
            if current['status'] == 'running':
                if isinstance(exc, ProcessingInterrupted):
                    self._save(job_id, current['output'], 'queued' if self.shutdown_requested else 'blocked',
                               current['current_step'], error='Application restarting' if self.shutdown_requested else 'Processing paused')
                elif isinstance(exc, SourceUnavailable):
                    output = current['output']
                    attempts = output.get('automation_retry', {}).get('failed_attempts', 0) + 1
                    delay = (60, 300, 900)[attempts - 1] if attempts <= 3 else 1800
                    due = (datetime.fromisoformat(utcnow()) + timedelta(seconds=delay)).isoformat()
                    output['automation_retry'] = {'failed_attempts': attempts, 'next_attempt_at': due,
                                                  'maximum_attempts': None}
                    self._save(job_id, output, 'retry_scheduled', current['current_step'], error=str(exc))
                elif isinstance(exc, SourceAccessRequired):
                    output = current['output']
                    output['failure_code'] = 'source_access_required'
                    self._save(job_id, output, 'failed', current['current_step'], error=str(exc))
                else:
                    self._save(job_id, current['output'], 'failed', current['current_step'], error=str(exc))
        finally:
            self.active_job = None
        return True

    def _prepare(self, job):
        from clipping import media
        job_id, data, output = job['id'], job['payload'], job['output']
        folder = self.storage / 'jobs' / job_id
        folder.mkdir(parents=True, exist_ok=True)
        stages = [('source_path', 'source_ingest', media.ingest),
                  ('transcript_path', 'transcription', media.transcribe)]
        if data.get('auto_clip'):
            from clipping.planning import prepare_clip_plan
            stages.append(('selected_clip_plan', 'clip_planning', prepare_clip_plan))
        stages.append(('clip_path', 'render_and_quality_check', media.render))
        for checkpoint, step, action in stages:
            if self.get(job_id)['status'] != 'running':
                return
            if self.killed():
                self._save(job_id, output, 'blocked', step, error='Kill switch enabled')
                return
            if checkpoint not in output:
                self._save(job_id, output, 'running', step)
                try:
                    output.update(action(data, output, folder, self.storage))
                except media.TranscriptRequired as exc:
                    self._save(job_id, output, 'awaiting_transcript', step, error=str(exc))
                    return
                self._save(job_id, output, 'running', step)
        if self.get(job_id)['status'] != 'running':
            return
        package = folder / 'submission-package.json'
        preview = data.get('preview_only', False)
        caption = (output.get('clip_suggestions') or [{}])[0].get('caption') if preview else None
        package.write_text(json.dumps({'campaign': data['campaign'], 'caption': data.get('caption', ''),
            'clip_plan': output.get('selected_clip_plan') or data['clip_plan'],
            'clip_path': output['clip_path'], 'clip_sha256': output['clip_sha256'],
            'dry_run': data['dry_run'], 'submission_status': 'not_submitted',
            **({'preview_only': True, 'caption': caption or data.get('caption', ''),
                'source_selection': output.get('source_selection'),
                'instructions': 'Private local preview complete. Campaign and reposting authorization are not recorded.'}
               if preview else {'instructions': 'Publish the reviewed clip, then submit its public URL in the selected campaign.'})},
            indent=2), encoding='utf-8')
        output['package_path'] = package.relative_to(self.storage).as_posix()
        if preview:
            output['preview_only'] = True
            output['caption'] = caption or data.get('caption', '')
            self._save(job_id, output, 'completed', 'preview_complete')
        elif not output.get('approvals', {}).get('clip_review', {}).get('approved'):
            self._save(job_id, output, 'awaiting_clip_approval', 'clip_review')
        elif data['dry_run']:
            output['dry_run'] = True
            self._save(job_id, output, 'completed', 'dry_run_complete')
        else:
            approval = output['approvals']['clip_review']
            if media.file_hash(self.artifact(job_id, 'clip')) != approval['fingerprint']:
                raise ValueError('Approved clip changed; create a fresh job for review')
            self._save(job_id, output, 'awaiting_publication', 'publication')
