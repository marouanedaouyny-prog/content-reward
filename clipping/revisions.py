"""Immutable local caption revisions of retained, completed clipping jobs."""

import copy
import hashlib
import json
import os
import re
from pathlib import Path

from app.repositories.database import timestamp
from app.repositories.store import Store, encode
from clipping import media, orchestrator
from clipping.caption_review import assess_captions
from clipping.library import niche_folder, niche_routing
from clipping.planning import chapter_conflicts
from clipping.quality.validation import validate_candidate
from clipping.recovery import _assert_revision, _install, _safe_path, _validate_assets
from clipping.workflow import ClippingWorkflow, digest


def _transcript(path, parent, duration):
    path = Path(path).absolute()
    # Explicit local files may live outside storage, but links and unbounded input
    # are not accepted. Never follow an operator-supplied URL or media source.
    if (not path.is_file() or path.stat().st_size > 2_000_000
            or any(item.is_symlink() for item in (path, *path.parents))):
        raise ValueError('invalid_caption_revision_file')
    raw = path.read_bytes()
    def nonfinite(value):
        raise ValueError('nonfinite_caption_revision')
    data = json.loads(raw.decode('utf-8-sig'), parse_constant=nonfinite)
    if not isinstance(data, dict) or not isinstance(data.get('segments'), list):
        raise ValueError('caption_revision_requires_segments')
    if data.get('source_sha256', parent['output']['source_sha256']) != parent['output']['source_sha256']:
        raise ValueError('caption_revision_source_hash_disagreement')
    if data.get('source_job_id', parent['id']) != parent['id']:
        raise ValueError('caption_revision_source_job_disagreement')
    rows = data['segments']
    if (not 1 <= len(rows) <= 500 or sum(len(row.get('words', [])) for row in rows
            if isinstance(row, dict)) > 5000):
        raise ValueError('caption_revision_too_many_segments')
    segments = media.validate_segments(rows, duration)
    provenance = {key: value for key, value in data.items() if key != 'segments'}
    return segments, hashlib.sha256(raw).hexdigest(), provenance


def _parent_artifacts(storage, parent):
    output = parent['output']
    for name in ('source', 'transcript', 'clip', 'subtitle', 'styled_subtitle'):
        if name == 'styled_subtitle' and name + '_path' not in output:
            continue
        path = _safe_path(storage / output[name + '_path'], storage)
        if (not output.get(name + '_sha256') or not path.is_file()
                or media.file_hash(path) != output[name + '_sha256']):
            raise ValueError('parent_artifact_integrity_failed')


def _no_other_pending(engine, child_id=None):
    with engine.connection() as db:
        pending = db.execute("""SELECT 1 FROM clipping_job WHERE
            status IN ('queued','running','retry_scheduled') AND id != ? LIMIT 1""",
            (child_id or '',)).fetchone()
    if pending:
        raise ValueError('caption_revision_pending_jobs')
    if engine.killed() or engine.shutdown_requested:
        raise ValueError('caption_revision_kill_switch')


def _write_exports(folder, state):
    warnings = []
    for path, value in [(folder / 'order.json', state), (folder / 'result.json', state.get('result'))]:
        if value is None:
            continue
        try:
            _safe_path(path, folder.parent.parent)
            orchestrator.atomic_json(path, value)
        except (OSError, ValueError):
            warnings.append('manifest_export_pending')
    return warnings


def _result(clip, *, status, warnings=None):
    return {'status': status, 'clip_id': clip['id'], 'clip': clip['path'],
            'subtitles': clip['subtitles'], 'post_caption': clip['caption'],
            'caption_revision': clip['settings']['caption_revision'],
            'review': clip['settings']['review'], 'human_review_required': True,
            'publishing_enabled': False, 'network_used': False, 'warnings': warnings or []}


def _commit(store, state, revision, parent, child, result, settings, provenance):
    state = copy.deepcopy(state)
    parent_id, child_id = parent['id'], child['id']
    for entry in state['clip_entries']:
        if entry.get('job_id') == parent_id:
            entry.update(job_id=child_id, post_caption=result['post_caption'], caption_revision=provenance)
            if provenance.get('niche_review') is not None:
                entry['niche_review'] = provenance['niche_review']
    def replaced(rows):
        return [dict(row, **result) if row.get('job_id') == parent_id else row for row in rows]
    state['batch_results'] = replaced(state.get('batch_results', []))
    if isinstance(state.get('result'), dict) and isinstance(state['result'].get('clips'), list):
        state['result']['clips'] = replaced(state['result']['clips'])
    if state.get('job_id') == parent_id:
        state['job_id'] = child_id
    state.setdefault('caption_revisions', []).append(provenance)
    state['updated_at'] = timestamp()
    with store.connection(write=True) as db:
        current = db.execute('SELECT status,settings FROM clips WHERE id=?', (parent_id,)).fetchone()
        if current is None or current['status'] != parent['status']:
            raise ValueError('caption_revision_parent_changed')
        db.execute('INSERT INTO clips VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (child_id, parent['order_id'], parent['source_id'], parent['moment_id'],
             result['clip'], result['subtitles'], child['output']['clip_sha256'], result['post_caption'],
             parent['caption_style'], parent['framing'], 'READY', timestamp(), encode(settings)))
        old_settings = json.loads(current['settings'])
        old_settings['superseded_by'] = child_id
        db.execute("UPDATE clips SET status='superseded',settings=? WHERE id=?",
                   (encode(old_settings), parent_id))
        store.save_order(state, expected_revision=revision, connection=db, sync_candidates=False)
    return state


def revise_clip(storage, clip_id, transcript_path, *, post_caption=None, niche_review=None):
    """Render one local correction, retaining the parent and its logical count.

    Only a successful full export review promotes the child. Failures retain a
    separate child job for evidence/retry and leave authoritative delivery alone.
    No acquisition, publishing or unrelated queue consumption is performed.
    """
    storage = Path(storage).absolute()
    store = Store(_safe_path(storage / 'content-reward.db', storage))
    initial = store.get_clip(clip_id)
    folder = _safe_path(storage / 'orders' / initial['order_id'], storage)
    _safe_path(folder / 'controller.lock', storage)
    with orchestrator.order_lock(folder):
        parent_clip = store.get_clip(clip_id)
        state, revision = store.read_order(parent_clip['order_id'])
        engine = ClippingWorkflow(_safe_path(folder / 'workflow.db', storage), storage)
        parent = engine.get(clip_id)
        if parent['status'] != 'completed' or parent['payload'].get('dry_run') is not False:
            raise ValueError('caption_revision_requires_completed_real_job')
        _parent_artifacts(storage, parent)
        if parent['output']['clip_sha256'] != parent_clip['sha256']:
            raise ValueError('parent_clip_hash_disagreement')
        segments, input_hash, supplied_provenance = _transcript(
            transcript_path, parent, parent['output']['source_duration'])
        caption = parent_clip['caption'] if post_caption is None else post_caption
        if not isinstance(caption, str) or not caption.strip() or len(caption) > 20_000:
            raise ValueError('invalid_revision_post_caption')
        request_hash = digest(dict(parent=clip_id, transcript_sha256=input_hash,
                                   post_caption=caption, niche_review=niche_review))
        if parent_clip['status'] == 'superseded':
            current = store.get_clip(parent_clip['settings']['superseded_by'])
            if current['settings'].get('caption_revision', {}).get('request_hash') != request_hash:
                raise ValueError('caption_revision_use_current_clip')
            _parent_artifacts(storage, engine.get(current['id']))
            from clipping.library import clip_availability
            if not clip_availability(current)['available']:
                raise ValueError('caption_revision_delivery_changed')
            return _result(current, status='already_revised', warnings=_write_exports(folder, state))
        if parent_clip['status'] != 'READY':
            raise ValueError('caption_revision_requires_ready_clip')
        entries = [entry for entry in state.get('clip_entries', []) if entry.get('job_id') == clip_id]
        if len(entries) != 1:
            raise ValueError('caption_revision_current_entry_missing')
        entry = entries[0]
        plan = entry['local_clip_plan']
        if (plan != parent['payload']['clip_plan']
                or parent['payload'].get('caption_style') != parent_clip['caption_style']
                or parent['payload'].get('framing_mode') != parent_clip['framing']):
            raise ValueError('caption_revision_saved_settings_disagreement')
        if not validate_candidate(entry['moment'], strict=True).passed:
            raise ValueError('caption_revision_candidate_quality_failed')
        source = entry.get('source') or state.get('source_selection') or {}
        metadata = source
        if entry.get('metadata_path'):
            path = _safe_path(folder / entry['metadata_path'], storage)
            if path.stat().st_size > 8_000_000:
                raise ValueError('source_metadata_too_large')
            metadata = json.loads(path.read_text(encoding='utf-8'))
            if metadata.get('id') != source.get('id'):
                raise ValueError('source_metadata_disagreement')
        if chapter_conflicts(entry['source_clip_plan'], metadata.get('chapters'),
                             source_duration=metadata.get('duration')):
            raise ValueError('caption_revision_chapter_excluded')
        reference = parent['payload'].get('source_reference')
        if not reference:
            raise ValueError('caption_revision_independent_source_cues_missing')
        media.validate_segments(reference, parent['output']['source_duration'])
        assessment = assess_captions(segments, plan['start_seconds'], plan['duration_seconds'], reference)
        if not assessment['passed']:
            raise ValueError('caption_revision_source_caption_quality_failed')
        review_decision = niche_review if niche_review is not None else entry.get('niche_review')
        routing = niche_routing(source, state['config'].get('niche'),
            excerpt=entry['moment'].get('source_excerpt', ''), review=review_decision)
        if niche_review is None and parent_clip['settings'].get('delivery_niche'):
            routing = parent_clip['settings'].get('niche_routing') or dict(
                niche=parent_clip['settings']['delivery_niche'], basis='saved_delivery_niche', needs_review=False)
        number = int(parent_clip['settings'].get('caption_revision', {}).get('revision_number', 0)) + 1
        provenance = dict(parent_clip_id=clip_id, logical_clip_number=entry['number'], revision_number=number,
            request_hash=request_hash, transcript_sha256=input_hash, transcript_origin='operator_supplied',
            supplied_provenance=supplied_provenance, niche_review=review_decision, created_at=timestamp())
        payload = copy.deepcopy(parent['payload'])
        for key in ('source_url', 'transcript_srt', 'auto_clip', 'research_keywords'):
            payload.pop(key, None)
        payload.update(source_path=parent['output']['source_path'], transcript=segments,
            dry_run=False, preview_only=True, caption=caption, caption_revision=provenance)
        key = f'caption-revision:{clip_id}:{request_hash}'
        with engine.connection() as db:
            row = db.execute('SELECT id FROM clipping_job WHERE idempotency_key=?', (key,)).fetchone()
        existing_id = row['id'] if row else None
        _no_other_pending(engine, existing_id)
        # Stable provenance must survive retries of the same request fingerprint.
        if existing_id:
            child = engine.get(existing_id)
            provenance = child['payload']['caption_revision']
        else:
            child = engine.create(payload, key)
        if child['status'] in ('failed', 'blocked'):
            child = engine.retry(child['id'])
        if child['status'] != 'completed':
            _no_other_pending(engine, child['id'])
            engine.consume_once(job_id=child['id'])
            child = engine.get(child['id'])
        if child['status'] != 'completed':
            raise ValueError('caption_revision_child_incomplete')
        review_job = {**child, 'output': dict(child['output'], selected_clip_plan=plan)}
        review = orchestrator.verify_export(engine, review_job, folder / 'caption-revisions' / child['id'])
        if review.get('passed') is not True:
            raise ValueError('caption_revision_export_review_failed')
        def unchanged():
            _assert_revision(storage, state['id'], revision)
            _parent_artifacts(storage, parent)
            _parent_artifacts(storage, child)
            _no_other_pending(engine, child['id'])
        unchanged()
        delivery = Path(state.get('delivery_dir') or state['config'].get('delivery_dir')
                        or Path(__file__).resolve().parents[1] / 'clips').absolute()
        original = _safe_path(Path(parent_clip['path']), delivery)
        destination = niche_folder(delivery, routing['niche']) if niche_review is not None else original.parent
        stem = re.sub(r'-r\d+$', '', original.stem) + f'-r{number}'
        target = _safe_path(destination / (stem + '.mp4'), delivery)
        assets = [(target, engine.artifact(child['id'], 'clip'), child['output']['clip_sha256']),
            (target.with_suffix('.srt'), engine.artifact(child['id'], 'subtitles'), child['output']['subtitle_sha256']),
            (target.with_name(stem + '-caption.txt'), caption.encode('utf-8'),
             hashlib.sha256(caption.encode('utf-8')).hexdigest())]
        if child['output'].get('styled_subtitle_path'):
            assets.append((target.with_suffix('.ass'), engine.safe_path(child['output']['styled_subtitle_path']),
                           child['output']['styled_subtitle_sha256']))
        _validate_assets(storage, delivery, assets)
        previously_absent = [target for target, _, _ in assets if not target.exists()]
        _install(assets, delivery, unchanged)
        installed = [(target, target.stat()) for target in previously_absent]
        provenance = dict(provenance, clip_id=child['id'])
        result = dict(job_id=child['id'], clip=str(target), subtitles=str(target.with_suffix('.srt')),
            post_caption=caption, review=review, caption_revision=provenance,
            delivery_niche=routing['niche'], niche_routing=routing)
        settings = dict(parent_clip['settings'], review=review, caption_revision=provenance,
            delivery_niche=routing['niche'], niche_routing=routing,
            delivery_hashes=dict(video=assets[0][2], subtitles=assets[1][2], post_caption=assets[2][2]))
        settings.pop('superseded_by', None)
        try:
            unchanged()
            state = _commit(store, state, revision, parent_clip, child, result, settings, provenance)
        except BaseException:
            # A domain transaction failure must not leave a delivered correction.
            # Preserve pre-existing files, replacements and any committed child.
            with store.connection() as db:
                committed = db.execute('SELECT 1 FROM clips WHERE id=?', (child['id'],)).fetchone()
            if not committed:
                for target, identity in reversed(installed):
                    if target.exists() and os.path.samestat(identity, target.stat()):
                        target.unlink()
            raise
        return _result(store.get_clip(child['id']), status='revised', warnings=_write_exports(folder, state))
