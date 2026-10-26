"""Recover retained local exports without resuming discovery or rewriting history."""

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from clipping import media, orchestrator
from clipping.caption_review import assess_captions
from clipping.captions import cues_for_window
from clipping.pipeline.checkpoints import verified_checkpoints
from clipping.planning import chapter_conflicts
from clipping.quality.validation import validate_candidate


def _linked(path):
    """Include Windows junctions/reparse points and multiply linked files."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            or stat.S_ISREG(info.st_mode) and info.st_nlink > 1)


def _safe_path(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    if path == root or not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('unsafe_artifact_path')
    if any(_linked(item) for item in (path, *path.parents)):
        raise ValueError('linked_artifact_path')
    return path


def _read_connection(path):
    # Keep committed WAL data authoritative. SQLite may maintain native -wal/-shm
    # lock bookkeeping even for mode=ro (https://www.sqlite.org/wal.html).
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    return closing(connection)


def _snapshot(storage, order_id):
    path = _safe_path(storage / 'content-reward.db', storage)
    with _read_connection(path) as db:
        row = db.execute('SELECT state,revision FROM orders WHERE id=?', (order_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown saved order')
        clips = [dict(item) for item in db.execute('SELECT * FROM clips WHERE order_id=?', (order_id,))]
    return json.loads(row['state']), row['revision'], clips


def _assert_revision(storage, order_id, revision):
    with _read_connection(storage / 'content-reward.db') as db:
        row = db.execute('SELECT revision FROM orders WHERE id=?', (order_id,)).fetchone()
    if row is None or row['revision'] != revision:
        raise ValueError('order_revision_changed')


class _ArtifactReader:
    """The export reviewer needs path resolution, never a mutable workflow engine."""

    def __init__(self, storage):
        self.storage = storage

    def safe_path(self, relative):
        return _safe_path(self.storage / relative, self.storage)


def _job(storage, order_folder, job_id):
    path = _safe_path(order_folder / 'workflow.db', storage)
    with _read_connection(path) as db:
        row = db.execute('SELECT id,status,payload,output FROM clipping_job WHERE id=?', (job_id,)).fetchone()
    if row is None or row['status'] != 'completed':
        raise ValueError('completed_job_missing')
    return dict(row) | {'payload': json.loads(row['payload']), 'output': json.loads(row['output'])}


def _inspect(storage, folder, clip, entry, delivery):
    job = _job(storage, folder, clip['id'])
    output, payload = job['output'], job['payload']
    for key in ('source', 'transcript', 'clip', 'subtitle', 'styled_subtitle'):
        if key == 'styled_subtitle' and key + '_path' not in output:
            continue
        if not output.get(key + '_sha256'):
            raise ValueError('recorded_hash_missing')
        _safe_path(storage / output[key + '_path'], storage)
    _, invalid = verified_checkpoints(output, storage)
    if invalid:
        raise ValueError('retained_artifact_integrity_failed')
    if output['clip_sha256'] != clip['sha256']:
        raise ValueError('clip_record_hash_disagreement')
    if (payload.get('caption_style') != clip['caption_style']
            or payload.get('framing_mode') != clip['framing']):
        raise ValueError('saved_settings_disagreement')
    plan = entry['local_clip_plan']
    if plan != payload['clip_plan']:
        raise ValueError('saved_clip_plan_disagreement')
    candidate = validate_candidate(entry['moment'], strict=True).model_dump()
    metadata = entry.get('source') or {}
    if entry.get('metadata_path'):
        path = _safe_path(folder / entry['metadata_path'], storage)
        if path.stat().st_size > 8_000_000:
            raise ValueError('source_metadata_too_large')
        metadata = json.loads(path.read_text(encoding='utf-8'))
        if metadata.get('id') != (entry.get('source') or {}).get('id'):
            raise ValueError('source_metadata_disagreement')
    source_plan = entry.get('source_clip_plan') or entry['moment']['clip_plan']
    conflicts = chapter_conflicts(source_plan, metadata.get('chapters'),
                                   source_duration=metadata.get('duration'))
    chapter_assessment = {'passed': not conflicts, 'source_clip_plan': source_plan,
                          'available_chapters': len(metadata['chapters'])
                              if isinstance(metadata.get('chapters'), list) else 0,
                          'conflicts': conflicts, 'coordinate_system': 'source_seconds'}
    transcript = json.loads((storage / output['transcript_path']).read_text(encoding='utf-8'))
    segments = media.validate_segments(transcript['segments'], output['source_duration'])
    reference = payload.get('source_reference')
    if not reference:
        raise ValueError('independent_source_cues_missing')
    media.validate_segments(reference, output['source_duration'])
    captions = assess_captions(segments, plan['start_seconds'], plan['duration_seconds'], reference)
    reference_cues = cues_for_window(reference, plan['start_seconds'], plan['duration_seconds'])
    duration = plan['duration_seconds']
    removal = output.get('silence_removal')
    if isinstance(removal, dict) and removal.get('applied'):
        from clipping import silence
        reference_cues = silence.remap_cues(reference_cues, removal['gaps'])
        duration -= removal['removed_seconds']
    subtitle = storage / output['subtitle_path']
    displayed = assess_captions(media.parse_srt(subtitle.read_text(encoding='utf-8')),
                                0, duration, reference_cues)
    video_target = _safe_path(Path(clip['path']), delivery)
    subtitle_target = _safe_path(Path(clip['subtitles']), delivery)
    caption_target = _safe_path(video_target.with_name(video_target.stem + '-caption.txt'), delivery)
    caption_bytes = clip['caption'].encode('utf-8')
    saved_settings = json.loads(clip['settings'])
    recorded_caption_hash = (saved_settings.get('delivery_hashes') or {}).get('post_caption')
    if recorded_caption_hash:
        # Windows text-mode delivery historically wrote CRLF. Reconstruct only
        # the saved caption's newline variants, and require the recorded hash;
        # never accept an arbitrary existing file merely because it is present.
        windows_bytes = clip['caption'].replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')
        caption_bytes = next((value for value in (caption_bytes, windows_bytes)
            if hashlib.sha256(value).hexdigest() == recorded_caption_hash), None)
        if caption_bytes is None:
            raise ValueError('post_caption_record_hash_disagreement')
    assets = [(video_target, storage / output['clip_path'], clip['sha256']),
              (subtitle_target, subtitle, output['subtitle_sha256']),
              (caption_target, caption_bytes, hashlib.sha256(caption_bytes).hexdigest())]
    if output.get('styled_subtitle_path'):
        assets.append((_safe_path(video_target.with_suffix('.ass'), delivery),
                       storage / output['styled_subtitle_path'], output['styled_subtitle_sha256']))
    _validate_assets(storage, delivery, assets)
    result = {'candidate_assessment': candidate, 'chapter_assessment': chapter_assessment,
              'caption_assessment': captions,
              'displayed_caption_assessment': displayed,
              'violations': ([] if candidate['passed'] else ['candidate_quality_failed'])
                  + ([] if chapter_assessment['passed'] else ['candidate_chapter_excluded'])
                  + ([] if captions['passed'] else ['source_caption_quality_failed'])
                  + ([] if displayed['passed'] else ['displayed_caption_quality_failed'])}
    return result, job, assets


def _validate_assets(storage, delivery, assets):
    if len({target for target, _, _ in assets}) != len(assets):
        raise ValueError('delivery_paths_overlap')
    for target, _, checksum in assets:
        _safe_path(target, delivery)
        if target.resolve().is_relative_to(storage.resolve()):
            raise ValueError('protected_storage_destination')
        if target.exists() and (not target.is_file() or media.file_hash(target) != checksum):
            raise ValueError('existing_delivery_changed')


def _organized_assets(assets, delivery, source, chosen, *, excerpt=None, review=None):
    from clipping.library import niche_folder, niche_routing, route_niche
    routing = niche_routing(source, chosen, excerpt=excerpt, review=review) if review is not None else None
    niche = routing['niche'] if routing is not None else route_niche(source, chosen)
    folder = _safe_path(niche_folder(delivery, niche), delivery)
    targets = {target: (source, checksum) for target, source, checksum in assets}
    combined = list(assets)
    for target, retained, checksum in assets:
        mirror = _safe_path(folder / target.name, delivery)
        if mirror in targets:
            if targets[mirror][1] != checksum:
                raise ValueError('delivery_paths_overlap')
            continue
        targets[mirror] = (retained, checksum)
        combined.append((mirror, retained, checksum))
    result = {'library_path': str(folder / assets[0][0].name),
              'library_subtitles': str(folder / assets[1][0].name), 'delivery_niche': niche}
    if routing is not None:
        result['niche_routing'] = routing
    return combined, result


def _install(assets, delivery, revision_check):
    """Stage a clip's whole delivery; exclusive links avoid clobbering racing writes."""
    staged, installed = [], []
    try:
        for target, source, checksum in assets:
            _safe_path(target, delivery)
            if target.exists():
                if media.file_hash(target) != checksum:
                    raise ValueError('existing_delivery_changed')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            _safe_path(target, delivery)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.' + target.name + '.',
                                             suffix='.recovery-tmp', delete=False) as stream:
                temporary = Path(stream.name)
            staged.append((temporary, target, checksum))
            if isinstance(source, bytes):
                temporary.write_bytes(source)
            else:
                shutil.copyfile(source, temporary)
            if media.file_hash(temporary) != checksum:
                raise ValueError('staged_copy_integrity_failed')
        revision_check()
        for temporary, target, checksum in staged:
            _safe_path(target, delivery)
            revision_check()
            os.link(temporary, target)
            installed.append((target, target.stat()))
        return bool(installed)
    except BaseException:
        for target, identity in reversed(installed):
            # Never remove a replacement created by another process during rollback.
            if target.exists() and os.path.samestat(identity, target.stat()):
                target.unlink()
        raise
    finally:
        for temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)


def _recover(storage, order_id, *, restore, organize):
    state, revision, clips = _snapshot(storage, order_id)
    folder = _safe_path(storage / 'orders' / order_id, storage)
    config = state['config']
    delivery = Path(state.get('delivery_dir') or config.get('delivery_dir')
                    or Path(__file__).resolve().parents[1] / 'clips').absolute()
    entries = {entry.get('job_id'): entry for entry in state.get('clip_entries', [])}
    report = {'order_id': order_id, 'order_revision': revision, 'mode': 'restore' if restore else 'audit',
              'organized': organize,
              'historical_status': state['status'], 'historical_stage': state['stage'],
              'historical_completed_clip_count': state.get('completed_clip_count', 0),
              'publishing_enabled': False, 'network_used': False, 'human_review_required': True,
              'speech_accuracy': 'not_verified', 'clips': [], 'eligible_count': 0,
              'restored_count': 0, 'already_present_count': 0, 'blocked_count': 0,
              'full_export_review_pending': not restore,
              'note': 'Historical records are unchanged. Recovery is not speech or editorial approval.'}
    evidence = folder / 'recovery' / uuid.uuid4().hex
    for clip in sorted(clips, key=lambda item: entries.get(item['id'], {}).get('number', 0)):
        if clip.get('status') == 'superseded':
            continue
        item = {'clip_id': clip['id'], 'path': clip['path'], 'status': 'blocked', 'violations': []}
        report['clips'].append(item)
        entry = entries.get(clip['id'])
        try:
            if not entry:
                raise ValueError('saved_clip_entry_missing')
            item['number'] = entry['number']
            assessment, job, assets = _inspect(storage, folder, clip, entry, delivery)
            item.update(assessment)
            if item['violations']:
                continue
            report['eligible_count'] += 1
            item['status'] = 'eligible_pending_export_review'
            if not restore:
                continue
            library = {}
            if organize:
                settings = json.loads(clip['settings'])
                source = entry.get('source') or settings.get('source') or {}
                assets, library = _organized_assets(assets, delivery, source, config.get('niche'),
                    excerpt=entry['moment'].get('source_excerpt'), review=entry.get('niche_review'))
                _validate_assets(storage, delivery, assets)
            _assert_revision(storage, order_id, revision)
            review_folder = _safe_path(evidence / ('review-' + uuid.uuid4().hex), storage)
            _safe_path(evidence / 'report.json', storage)
            try:
                review = orchestrator.verify_export(_ArtifactReader(storage),
                    job | {'output': job['output'] | {'selected_clip_plan': entry['local_clip_plan']}}, review_folder)
            except (ValueError, OSError, subprocess.SubprocessError):
                raise ValueError('export_review_failed') from None
            if review.get('passed') is not True:
                raise ValueError('export_review_failed')
            item['export_review'] = review
            _assert_revision(storage, order_id, revision)
            installed = _install(assets, delivery, lambda: _assert_revision(storage, order_id, revision))
            item['status'] = 'restored' if installed else 'already_present'
            item.update(library)
            report['restored_count' if installed else 'already_present_count'] += 1
        except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as error:
            item['status'] = 'blocked'
            known = {'recorded_hash_missing', 'retained_artifact_integrity_failed', 'clip_record_hash_disagreement',
                     'saved_settings_disagreement', 'saved_clip_plan_disagreement', 'independent_source_cues_missing',
                     'delivery_paths_overlap', 'existing_delivery_changed', 'saved_clip_entry_missing',
                     'order_revision_changed', 'export_review_failed', 'unsafe_artifact_path', 'linked_artifact_path',
                     'completed_job_missing', 'staged_copy_integrity_failed', 'protected_storage_destination'}
            known.update(('source_metadata_too_large', 'source_metadata_disagreement'))
            item['violations'].append(str(error) if str(error) in known else 'local_recovery_failed')
    report['blocked_count'] = sum(item['status'] == 'blocked' for item in report['clips'])
    report['status'] = 'partial' if report['blocked_count'] else 'audited' if not restore else 'restored'
    if restore:
        path = _safe_path(evidence / 'report.json', storage)
        path.parent.mkdir(parents=True, exist_ok=True)
        report['report_path'] = str(path)
        report['created_at'] = datetime.now(timezone.utc).isoformat()
        orchestrator.atomic_json(path, report)
    return report


def recover_order(storage, order_id, *, restore=False, organize=False):
    """Audit DB-backed originals; explicitly restore passing copies with no acquisition."""
    if organize and not restore:
        raise ValueError('Organizing review copies requires explicit restore')
    order_id = str(uuid.UUID(order_id))
    storage = Path(storage).absolute()
    folder = _safe_path(storage / 'orders' / order_id, storage)
    if not restore:
        return _recover(storage, order_id, restore=False, organize=False)
    _safe_path(folder / 'controller.lock', storage)
    with orchestrator.order_lock(folder):
        return _recover(storage, order_id, restore=True, organize=organize)
