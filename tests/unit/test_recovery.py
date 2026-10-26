"""Local recovery must not turn historical completion into unchecked delivery."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

import pytest

from app.repositories.store import Store


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def retained(tmp_path, monkeypatch):
    storage = tmp_path / 'storage'
    delivery = tmp_path / 'clips'
    order_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
    folder = storage / 'orders' / order_id
    folder.mkdir(parents=True)
    job_folder = storage / 'jobs' / job_id
    job_folder.mkdir(parents=True)
    text = 'A team needs a clear plan. Assign one owner to every decision.'
    segments = [{'start': 0, 'end': 20, 'text': text}]
    output = {'source_duration': 20, 'synthetic_source': False,
              'transcript_origin': 'faster_whisper:en', 'caption_style': 'colorized',
              'framing_mode': 'fit'}
    assets = {'source': ('source.mp4', b'retained bounded source'),
              'transcript': ('transcript.json', json.dumps({'segments': segments}).encode()),
              'clip': ('clip.mp4', b'verified historical export'),
              'subtitle': ('subtitles.srt', ('1\n00:00:00,000 --> 00:00:20,000\n' + text + '\n').encode()),
              'styled_subtitle': ('subtitles.ass', b'historical lime caption style')}
    for key, (name, content) in assets.items():
        path = job_folder / name
        path.write_bytes(content)
        output[key + '_path'] = path.relative_to(storage).as_posix()
        output[key + '_sha256'] = digest(content)
    plan = {'start_seconds': 0, 'duration_seconds': 20, 'aspect_ratio': '9:16'}
    quality = dict.fromkeys(('ending_question', 'filler_opening', 'context_dependent_opening',
                            'mid_sentence_opening', 'promotional', 'intro_or_outro', 'host_meta_setup'), False)
    quality.update(completed_ending=True, speech_ratio=1, largest_speech_gap=0)
    moment = {'clip_plan': plan, 'quality': quality, 'source_excerpt': text}
    payload = {'clip_plan': plan, 'source_reference': segments, 'dry_run': False,
               'preview_only': True, 'caption_style': 'colorized', 'framing_mode': 'fit'}
    entry = {'job_id': job_id, 'number': 1, 'local_clip_plan': plan, 'moment': moment}
    state = {'id': order_id, 'status': 'ready_for_review', 'stage': 'finished',
             'config': {'caption_style': 'colorized', 'framing_mode': 'fit',
                        'delivery_dir': str(delivery)}, 'delivery_dir': str(delivery),
             'clip_entries': [entry], 'batch_results': [{'job_id': job_id}],
             'completed_clip_count': 1, 'result': {'historical': True}}
    store = Store(storage / 'content-reward.db')
    store.save_order(state)
    target = delivery / 'historical-01.mp4'
    store.save_clip({'id': job_id, 'order_id': order_id, 'path': str(target),
                     'subtitles': str(target.with_suffix('.srt')), 'sha256': output['clip_sha256'],
                     'caption': 'Separate post caption.', 'caption_style': 'colorized', 'framing': 'fit'})
    workflow_db = folder / 'workflow.db'
    with closing(sqlite3.connect(workflow_db)) as db:
        with db:
            db.execute('CREATE TABLE clipping_job(id TEXT PRIMARY KEY,status TEXT,payload TEXT,output TEXT)')
            db.execute('INSERT INTO clipping_job VALUES(?,?,?,?)',
                       (job_id, 'completed', json.dumps(payload), json.dumps(output)))
    from clipping import orchestrator, media
    from clipping import sections
    def forbidden(*args, **kwargs):
        pytest.fail('Recovery attempted acquisition, rendering or network access')
    monkeypatch.setattr(orchestrator, 'check_environment', forbidden)
    monkeypatch.setattr(media, 'ingest', forbidden)
    monkeypatch.setattr(media, 'transcribe', forbidden)
    monkeypatch.setattr(media, 'render', forbidden)
    monkeypatch.setattr(sections, 'download_section', forbidden)
    monkeypatch.setattr(orchestrator, 'verify_export', lambda engine, job, folder:
                        {'passed': True, 'human_review_required': True, 'speech_accuracy': 'not_verified'})
    return {'storage': storage, 'delivery': delivery, 'order_id': order_id, 'job_id': job_id,
            'folder': folder, 'job_folder': job_folder, 'target': target, 'store': store,
            'state': state, 'payload': payload, 'output': output, 'workflow_db': workflow_db}


def tree_snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob('*') if path.is_file()
            and not path.name.endswith(('.db-wal', '.db-shm'))}


def update_job(fixture, field, value):
    with closing(sqlite3.connect(fixture['workflow_db'])) as db:
        with db:
            db.execute('UPDATE clipping_job SET ' + field + '=? WHERE id=?',
                       (json.dumps(value), fixture['job_id']))


def test_audit_is_read_only_and_uses_db_instead_of_manifest(retained):
    from clipping.recovery import recover_order
    (retained['folder'] / 'order.json').write_text('{"status":"contradictory"}')
    order_before = retained['store'].read_order(retained['order_id'])
    before = tree_snapshot(retained['storage'].parent)
    report = recover_order(retained['storage'], retained['order_id'])
    assert report['eligible_count'] == 1 and report['restored_count'] == 0
    assert report['clips'][0]['status'] == 'eligible_pending_export_review'
    assert report['historical_status'] == 'ready_for_review'
    assert tree_snapshot(retained['storage'].parent) == before
    assert retained['store'].read_order(retained['order_id']) == order_before
    assert not retained['delivery'].exists()


def test_restore_copies_all_sidecars_idempotently_without_changing_original_records(retained):
    from clipping.recovery import recover_order
    db_before = retained['store'].read_order(retained['order_id'])
    job_before = retained['workflow_db'].read_bytes()
    first = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert first['restored_count'] == 1 and first['blocked_count'] == 0
    target = retained['target']
    assert target.read_bytes() == b'verified historical export'
    assert target.with_suffix('.srt').read_bytes() == (retained['job_folder'] / 'subtitles.srt').read_bytes()
    assert target.with_suffix('.ass').read_bytes() == b'historical lime caption style'
    assert target.with_name(target.stem + '-caption.txt').read_text() == 'Separate post caption.'
    assert Path(first['report_path']).is_file()
    second = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert second['clips'][0]['status'] == 'already_present'
    assert retained['store'].read_order(retained['order_id']) == db_before
    assert retained['workflow_db'].read_bytes() == job_before


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_recovery_preserves_recorded_post_caption_newlines(retained, newline):
    from clipping.recovery import recover_order
    clip = retained['store'].get_clip(retained['job_id'])
    clip['caption'] = 'A separate caption.\n\nSource: Interview'
    content = clip['caption'].replace('\n', newline).encode('utf-8')
    clip['settings'] = {'delivery_hashes': {'post_caption': digest(content)}}
    retained['store'].save_clip(clip)
    with retained['store'].connection(write=True) as db:
        db.execute('UPDATE clips SET caption=? WHERE id=?', (clip['caption'], clip['id']))
    retained['delivery'].mkdir()
    caption = retained['target'].with_name('historical-01-caption.txt')
    caption.write_bytes(content)
    report = recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert report['blocked_count'] == 0
    assert caption.read_bytes() == content
    mirrored = Path(report['clips'][0]['library_path']).with_name('historical-01-caption.txt')
    assert mirrored.read_bytes() == content
    assert retained['store'].get_clip(clip['id']) == clip


def test_recovery_rejects_caption_hash_for_different_text(retained):
    from clipping.recovery import recover_order
    clip = retained['store'].get_clip(retained['job_id'])
    clip['settings'] = {'delivery_hashes': {'post_caption': digest(b'Different text')}}
    retained['store'].save_clip(clip)
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert not retained['target'].exists()


def test_audit_reads_committed_live_wal_instead_of_stale_main_database(retained):
    from clipping.recovery import recover_order
    with closing(sqlite3.connect(retained['storage'] / 'content-reward.db')) as writer:
        state = retained['state'] | {'status': 'insufficient_sources'}
        with writer:
            writer.execute('UPDATE orders SET state=? WHERE id=?',
                           (json.dumps(state), retained['order_id']))
        assert Path(str(retained['storage'] / 'content-reward.db') + '-wal').stat().st_size > 0
        report = recover_order(retained['storage'], retained['order_id'])
        assert report['historical_status'] == 'insufficient_sources'
        assert report['eligible_count'] == 1
        assert not (retained['folder'] / 'recovery').exists()
        assert not (retained['folder'] / 'controller.lock').exists()


@pytest.mark.parametrize('asset', ['source.mp4', 'transcript.json', 'clip.mp4', 'subtitles.srt', 'subtitles.ass'])
def test_changed_retained_artifact_blocks_delivery(retained, asset):
    from clipping.recovery import recover_order
    (retained['job_folder'] / asset).write_bytes(b'changed')
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1 and report['restored_count'] == 0
    assert not retained['target'].exists()


def test_missing_recorded_hash_never_grandfathers_a_checkpoint(retained):
    from clipping.recovery import recover_order
    output = retained['output'].copy()
    output.pop('source_sha256')
    update_job(retained, 'output', output)
    report = recover_order(retained['storage'], retained['order_id'])
    assert report['blocked_count'] == 1
    assert 'recorded_hash_missing' in report['clips'][0]['violations']


def test_existing_changed_delivery_is_never_overwritten(retained):
    from clipping.recovery import recover_order
    retained['delivery'].mkdir()
    subtitle = retained['target'].with_suffix('.srt')
    subtitle.write_text('operator correction')
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert subtitle.read_text() == 'operator correction'
    assert not retained['target'].exists()


def test_candidate_and_independent_source_disagreements_block_export_review(retained, monkeypatch):
    from clipping.recovery import recover_order
    from clipping import orchestrator
    monkeypatch.setattr(orchestrator, 'verify_export', lambda *args: pytest.fail('Invalid clip reached full review'))
    payload = retained['payload'].copy()
    payload['source_reference'] = [{'start': 0, 'end': 20,
        'text': 'This entirely different sentence discusses several unrelated events and people today.'}]
    update_job(retained, 'payload', payload)
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert report['clips'][0]['caption_assessment']['passed'] is False
    update_job(retained, 'payload', retained['payload'])
    state = retained['store'].get_order(retained['order_id'])
    state['clip_entries'][0]['moment']['source_excerpt'] = "He hasn't spoken since he left Manchester United."
    retained['store'].save_order(state)
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert 'standalone' in report['clips'][0]['candidate_assessment']['violations']


def test_missing_independent_cues_blocks_recovery(retained):
    from clipping.recovery import recover_order
    payload = retained['payload'].copy()
    payload.pop('source_reference')
    update_job(retained, 'payload', payload)
    assert recover_order(retained['storage'], retained['order_id'])['blocked_count'] == 1


@pytest.mark.parametrize(('text', 'violation'), [
    ('I believed I could be successful when I was younger, but let me tell you what.', 'no_pending_payoff'),
    ('Yes, sir. I agree. We should do a fight at the White House.', 'no_filler_or_weak_opening'),
])
def test_recovery_rejects_stale_boundary_flags_without_selecting_a_new_window(retained, monkeypatch, text, violation):
    from clipping import orchestrator
    from clipping.recovery import recover_order
    state = retained['store'].get_order(retained['order_id'])
    state['clip_entries'][0]['moment']['source_excerpt'] = text
    retained['store'].save_order(state)
    before = retained['store'].read_order(retained['order_id'])
    reviews = []
    monkeypatch.setattr(orchestrator, 'verify_export', lambda *args:
                        reviews.append(True) or {'passed': True})
    report = recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert report['blocked_count'] == 1 and report['restored_count'] == 0
    assert violation in report['clips'][0]['candidate_assessment']['violations']
    assert reviews == [] and not retained['target'].exists()
    assert retained['store'].read_order(retained['order_id']) == before


def test_failed_full_review_preserves_absent_deliveries(retained, monkeypatch):
    from clipping.recovery import recover_order
    from clipping import orchestrator
    def reject(*args):
        raise ValueError('Export review failed: full_decode')
    monkeypatch.setattr(orchestrator, 'verify_export', reject)
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert 'export_review_failed' in report['clips'][0]['violations']
    assert not retained['target'].exists()


def test_order_revision_change_during_review_prevents_delivery(retained, monkeypatch):
    from clipping.recovery import recover_order
    from clipping import orchestrator
    def changed(*args):
        state = retained['store'].get_order(retained['order_id'])
        state['action'] = 'Changed by another controller'
        retained['store'].save_order(state)
        return {'passed': True}
    monkeypatch.setattr(orchestrator, 'verify_export', changed)
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert 'order_revision_changed' in report['clips'][0]['violations']
    assert not retained['target'].exists()


def test_failed_sidecar_install_rolls_back_only_new_copies(retained, monkeypatch):
    from clipping import recovery
    retained['delivery'].mkdir()
    retained['target'].write_bytes(b'verified historical export')
    original_link = recovery.os.link
    calls = 0
    def fail_second(source, destination, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('simulated sidecar failure')
        return original_link(source, destination, *args, **kwargs)
    monkeypatch.setattr(recovery.os, 'link', fail_second)
    report = recovery.recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert retained['target'].read_bytes() == b'verified historical export'
    assert sorted(path.name for path in retained['delivery'].iterdir()) == [retained['target'].name]


def test_saved_destination_cannot_escape_delivery_root(retained):
    from clipping.recovery import recover_order
    clip = retained['store'].get_clip(retained['job_id'])
    outside = retained['storage'].parent / 'outside.mp4'
    retained['store'].save_clip(clip | {'path': str(outside)})
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert not outside.exists()


def test_saved_delivery_settings_cannot_target_original_job_storage(retained):
    from clipping.recovery import recover_order
    state = retained['store'].get_order(retained['order_id'])
    state['delivery_dir'] = str(retained['job_folder'])
    retained['store'].save_order(state)
    clip = retained['store'].get_clip(retained['job_id'])
    retained['store'].save_clip(clip | {'path': str(retained['job_folder'] / 'clip.mp4'),
                                      'subtitles': str(retained['job_folder'] / 'subtitles.srt')})
    before = tree_snapshot(retained['job_folder'])
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert tree_snapshot(retained['job_folder']) == before


def test_hardlinked_delivery_target_is_rejected_without_changing_its_other_name(retained):
    import os
    from clipping.recovery import recover_order
    retained['delivery'].mkdir()
    original = retained['storage'].parent / 'protected.mp4'
    original.write_bytes(b'verified historical export')
    os.link(original, retained['target'])
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert original.read_bytes() == b'verified historical export'
    assert not retained['target'].with_suffix('.srt').exists()


def test_linked_delivery_directory_is_rejected(retained, monkeypatch):
    from clipping import recovery
    original = recovery._linked
    monkeypatch.setattr(recovery, '_linked', lambda path:
                        path == retained['delivery'] or original(path))
    report = recovery.recover_order(retained['storage'], retained['order_id'], restore=True)
    assert report['blocked_count'] == 1
    assert not retained['target'].exists()


def test_organized_recovery_adds_niche_copies_and_keeps_saved_paths_and_settings(retained):
    from clipping.recovery import recover_order
    state = retained['store'].get_order(retained['order_id'])
    state['clip_entries'][0]['source'] = {'niches': ['Sport']}
    retained['store'].save_order(state)
    order_before = retained['store'].read_order(retained['order_id'])
    clip_before = retained['store'].get_clip(retained['job_id'])
    report = recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert report['restored_count'] == 1 and report['blocked_count'] == 0
    item = report['clips'][0]
    mirror = retained['delivery'] / 'sports' / retained['target'].name
    assert item['library_path'] == str(mirror)
    assert item['library_subtitles'] == str(mirror.with_suffix('.srt'))
    assert item['delivery_niche'] == 'sports'
    for name in [retained['target'].name, 'historical-01.srt', 'historical-01.ass', 'historical-01-caption.txt']:
        assert (retained['delivery'] / name).read_bytes() == (mirror.parent / name).read_bytes()
    assert retained['store'].read_order(retained['order_id']) == order_before
    assert retained['store'].get_clip(retained['job_id']) == clip_before
    repeat = recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert repeat['clips'][0]['status'] == 'already_present'


def test_organize_requires_explicit_restore_before_creating_lock_or_report(retained):
    from clipping.recovery import recover_order
    before = tree_snapshot(retained['storage'].parent)
    with pytest.raises(ValueError, match='restore'):
        recover_order(retained['storage'], retained['order_id'], organize=True)
    assert tree_snapshot(retained['storage'].parent) == before


def test_organized_recovery_uses_saved_chosen_niche_over_ambiguous_labels(retained):
    from clipping.recovery import recover_order
    state = retained['store'].get_order(retained['order_id'])
    state['config']['niche'] = 'Education'
    state['clip_entries'][0]['source'] = {'niches': ['Business', 'Education']}
    retained['store'].save_order(state)
    report = recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert report['clips'][0]['delivery_niche'] == 'education'
    assert (retained['delivery'] / 'education' / retained['target'].name).is_file()


def test_changed_niche_mirror_blocks_whole_group_without_creating_originals(retained):
    from clipping.recovery import recover_order
    mirror = retained['delivery'] / 'unclassified' / retained['target'].name
    mirror.parent.mkdir(parents=True)
    mirror.write_bytes(b'operator changed this copy')
    report = recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert report['blocked_count'] == 1
    assert mirror.read_bytes() == b'operator changed this copy'
    assert not retained['target'].exists()
    assert 'library_path' not in report['clips'][0]


def test_linked_niche_folder_blocks_original_and_mirror_writes(retained, monkeypatch):
    from clipping import recovery
    original = recovery._linked
    niche = retained['delivery'] / 'unclassified'
    monkeypatch.setattr(recovery, '_linked', lambda path: path == niche or original(path))
    report = recovery.recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert report['blocked_count'] == 1
    assert not retained['target'].exists()
    assert not niche.exists()


def test_failure_during_mirror_install_rolls_back_new_original_and_mirror_files(retained, monkeypatch):
    from clipping import recovery
    original_link = recovery.os.link
    def fail_mirror(source, destination, *args, **kwargs):
        if Path(destination).parent.name == 'unclassified' and Path(destination).suffix == '.srt':
            raise OSError('simulated niche mirror copy failure')
        return original_link(source, destination, *args, **kwargs)
    monkeypatch.setattr(recovery.os, 'link', fail_mirror)
    report = recovery.recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert report['blocked_count'] == 1
    assert not any(path.is_file() for path in retained['delivery'].rglob('*'))
    assert 'library_path' not in report['clips'][0]


@pytest.mark.parametrize('blocked', [True, False])
def test_recovery_rechecks_source_chapters_without_using_local_section_coordinates(retained, monkeypatch, blocked):
    from clipping import orchestrator
    from clipping.recovery import recover_order
    state = retained['store'].get_order(retained['order_id'])
    entry = state['clip_entries'][0]
    entry['source'] = {'id': 'fixture-source'}
    entry['metadata_path'] = 'source-captions/fixture-source/source.json'
    entry['source_clip_plan'] = {**entry['local_clip_plan'], 'start_seconds': 400}
    entry['moment']['clip_plan'] = entry['source_clip_plan']
    metadata = retained['folder'] / entry['metadata_path']
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({'id': 'fixture-source', 'duration': 1000,
        'chapters': [{'title': 'Intro', 'start_time': 410 if blocked else 0,
                      'end_time': 415 if blocked else 325}]}), encoding='utf-8')
    retained['store'].save_order(state)
    before = retained['store'].read_order(retained['order_id'])
    reviews = []
    monkeypatch.setattr(orchestrator, 'verify_export', lambda *args:
                        reviews.append(True) or {'passed': True})
    report = recover_order(retained['storage'], retained['order_id'], restore=True)
    if blocked:
        assert report['blocked_count'] == 1 and report['restored_count'] == 0
        assert 'candidate_chapter_excluded' in report['clips'][0]['violations']
        assert reviews == [] and not retained['target'].exists()
    else:
        assert report['restored_count'] == 1 and retained['target'].is_file()
        assert reviews == [True]
    assert retained['store'].read_order(retained['order_id']) == before


def test_organized_recovery_respects_explicit_entry_niche_review_without_changing_history(retained):
    from clipping.recovery import recover_order
    state = retained['store'].get_order(retained['order_id'])
    state['clip_entries'][0]['source'] = {'niches': ['Sport']}
    state['clip_entries'][0]['niche_review'] = {
        'niche': 'ai-technology', 'rationale': 'The reviewed moment discusses AI and creative work.'}
    retained['store'].save_order(state)
    before = retained['store'].read_order(retained['order_id'])
    report = recover_order(retained['storage'], retained['order_id'], restore=True, organize=True)
    assert report['clips'][0]['delivery_niche'] == 'ai-technology'
    assert (retained['delivery'] / 'ai-technology' / retained['target'].name).is_file()
    assert retained['store'].read_order(retained['order_id']) == before
