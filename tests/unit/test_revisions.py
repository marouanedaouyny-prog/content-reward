"""Caption corrections create a new reviewed export without rewriting its parent."""

import json
import shutil
from pathlib import Path

import pytest

from app.repositories.store import Store, moment_identifier
from clipping import media, orchestrator
from clipping.workflow import ClippingWorkflow


@pytest.fixture
def revision_case(tmp_path, monkeypatch):
    storage, delivery = tmp_path / 'storage', tmp_path / 'clips'
    controller = orchestrator.Controller(storage, orchestrator.Config(
        partial_downloads=True, clip_count=4, caption_style='colorized', delivery_dir=str(delivery)))
    engine = ClippingWorkflow(controller.folder / 'workflow.db', storage)
    retained = storage / 'bounded.mp4'
    retained.write_bytes(b'bounded retained local source')
    text = 'A team needs a clear plan. Assign one owner to every decision.'
    segments = [{'start': 0, 'end': 20, 'text': text}]
    plan = {'start_seconds': 0, 'duration_seconds': 20, 'aspect_ratio': '9:16'}
    source = {'id': 'source123', 'url': 'https://www.youtube.com/watch?v=source123',
              'title': 'An interview', 'niches': ['Business'], 'duration': 200}
    payload = {'campaign': {'title': 'Private highlight', 'url': source['url'],
        'platform': 'youtube', 'rules': 'Private local review.', 'rights_notes': 'Research preview.'},
        'preview_only': True, 'dry_run': False, 'source_path': 'bounded.mp4',
        'source_reference': segments, 'source_reference_origin': 'public_source_captions',
        'clip_plan': plan, 'caption': 'A separate post caption.', 'caption_style': 'colorized',
        'framing_mode': 'fit', 'language': 'en'}
    parent = engine.create(payload, 'parent')
    folder = storage / 'jobs' / parent['id']
    folder.mkdir(parents=True)
    output = {'source_duration': 20, 'synthetic_source': False, 'transcript_origin': 'faster_whisper:en'}
    for key, name, content in [('source', 'source.mp4', retained.read_bytes()),
        ('transcript', 'transcript.json', json.dumps({'segments': segments}).encode()),
        ('clip', 'clip.mp4', b'old export'), ('subtitle', 'subtitles.srt', b'old captions')]:
        path = folder / name
        path.write_bytes(content)
        output[key + '_path'], output[key + '_sha256'] = path.relative_to(storage).as_posix(), media.file_hash(path)
    with engine.connection() as db:
        db.execute("UPDATE clipping_job SET status='completed',output=? WHERE id=?",
                   (json.dumps(output), parent['id']))
    quality = dict.fromkeys(('ending_question', 'filler_opening', 'context_dependent_opening',
        'mid_sentence_opening', 'promotional', 'intro_or_outro', 'host_meta_setup'), False)
    quality.update(completed_ending=True, speech_ratio=1, largest_speech_gap=0)
    moment = {'clip_plan': plan, 'source_excerpt': text, 'quality': quality, 'note': 'Editorial selection.'}
    entry = {'number': 1, 'job_id': parent['id'], 'local_clip_plan': plan, 'source_clip_plan': plan,
             'moment': moment, 'source': source, 'post_caption': payload['caption'], 'source_offset': 0}
    result = {'number': 1, 'job_id': parent['id'], 'clip': str(delivery / 'old-01.mp4')}
    controller.update(clip_entries=[entry, {'number': 2, 'job_id': 'untouched'}], batch_results=[result],
        completed_clip_count=1, status='failed', result={'clips': [result], 'requested_clip_count': 4})
    store = Store(storage / 'content-reward.db')
    store.save_clip({'id': parent['id'], 'order_id': controller.state['id'], 'source_id': source['id'],
        'moment_id': moment_identifier(controller.state['id'], source['id'], plan),
        'path': str(delivery / 'old-01.mp4'), 'subtitles': str(delivery / 'old-01.srt'),
        'sha256': output['clip_sha256'], 'caption': payload['caption'], 'caption_style': 'colorized',
        'framing': 'fit', 'settings': {'source_clip_plan': plan, 'delivery_niche': 'business', 'source': source}})
    corrected = storage / 'operator.json'
    corrected.write_text(json.dumps({'origin': 'operator_supplied', 'segments': segments,
        'source_sha256': output['source_sha256'], 'source_job_id': parent['id'],
        'corrections': [{'text': 'AI is here to stay', 'evidence': 'user listening confirmation'}]}))

    def ingest(data, output, folder, storage):
        assert 'source_url' not in data and data['source_path'] == output_parent['source_path']
        target = folder / 'source.mp4'
        shutil.copyfile(storage / data['source_path'], target)
        return {'source_path': target.relative_to(storage).as_posix(), 'source_sha256': media.file_hash(target),
                'source_duration': 20, 'synthetic_source': False}

    def render(data, output, folder, storage):
        paths = {}
        for key, name, content in [('clip', 'clip.mp4', b'corrected export'),
            ('subtitle', 'subtitles.srt', b'1\n00:00:00,000 --> 00:00:20,000\n' + text.encode() + b'\n')]:
            path = folder / name
            path.write_bytes(content)
            paths.update({key + '_path': path.relative_to(storage).as_posix(), key + '_sha256': media.file_hash(path)})
        return paths

    reviews = []

    def verify(engine, job, folder):
        reviews.append(job['id'])
        assert job['payload']['source_reference'] == segments
        assert job['output']['transcript_origin'] == 'operator_supplied'
        assert job['payload']['preview_only'] and job['payload']['dry_run'] is False
        assert engine.get(parent['id'])['output'] == output_parent
        return {'passed': True, 'human_review_required': True, 'speech_accuracy': 'not_verified'}

    output_parent = output.copy()
    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(media, 'render', render)
    monkeypatch.setattr(orchestrator, 'verify_export', verify)
    return dict(storage=storage, delivery=delivery, controller=controller, engine=engine, store=store,
        parent=parent['id'], corrected=corrected, output=output, reviews=reviews)


def test_revision_preserves_parent_and_count_and_is_idempotent(revision_case):
    from clipping.revisions import revise_clip
    case = revision_case
    before = case['store'].get_order(case['controller'].state['id'])
    parent = case['engine'].get(case['parent'])
    artifacts = {key: (case['storage'] / value).read_bytes()
                 for key, value in parent['output'].items() if key.endswith('_path')}
    result = revise_clip(case['storage'], case['parent'], case['corrected'])
    child = result['clip_id']
    assert child != case['parent'] and Path(result['clip']).name == 'old-01-r1.mp4'
    assert case['engine'].get(case['parent']) == parent
    assert all((case['storage'] / parent['output'][key]).read_bytes() == content for key, content in artifacts.items())
    state = case['store'].get_order(before['id'])
    assert state['config'] == before['config'] and state['status'] == before['status']
    assert state['completed_clip_count'] == 1 and len(state['batch_results']) == 1
    assert state['clip_entries'][1] == before['clip_entries'][1]
    assert state['clip_entries'][0]['job_id'] == state['result']['clips'][0]['job_id'] == child
    assert case['store'].get_clip(case['parent'])['status'] == 'superseded'
    assert case['store'].get_clip(child)['settings']['caption_revision']['parent_clip_id'] == case['parent']
    second = revise_clip(case['storage'], case['parent'], case['corrected'])
    assert second['clip_id'] == child and second['status'] == 'already_revised'
    assert len(case['engine'].list()) == 2 and case['reviews'] == [child]
    from clipping.library import niche_library
    assert sum(group['clip_count'] for group in niche_library(case['store'], root=case['delivery'])['categories']) == 1


def test_failed_export_review_does_not_replace_parent_or_deliver(revision_case, monkeypatch):
    from clipping.revisions import revise_clip
    case = revision_case
    before = case['store'].read_order(case['controller'].state['id'])
    monkeypatch.setattr(orchestrator, 'verify_export', lambda *a: (_ for _ in ()).throw(ValueError('failed QC')))
    with pytest.raises(ValueError, match='failed QC'):
        revise_clip(case['storage'], case['parent'], case['corrected'])
    assert case['store'].read_order(before[0]['id']) == before
    assert len(case['store'].list_clips()) == 1 and not case['delivery'].exists()


@pytest.mark.parametrize('state', ['queued', 'running', 'retry_scheduled'])
def test_unrelated_pending_job_is_never_consumed(revision_case, state):
    from clipping.revisions import revise_clip
    case = revision_case
    job = case['engine'].create(case['engine'].get(case['parent'])['payload'], 'unrelated')
    with case['engine'].connection() as db:
        db.execute('UPDATE clipping_job SET status=? WHERE id=?', (state, job['id']))
    with pytest.raises(ValueError, match='pending_jobs'):
        revise_clip(case['storage'], case['parent'], case['corrected'])
    assert case['engine'].get(job['id'])['status'] == state and len(case['engine'].list()) == 2


def test_kill_switch_blocks_before_child_creation(revision_case):
    from clipping.revisions import revise_clip
    case = revision_case
    case['engine'].set_kill_switch(True)
    with pytest.raises(ValueError, match='kill_switch'):
        revise_clip(case['storage'], case['parent'], case['corrected'])
    assert len(case['engine'].list()) == 1


@pytest.mark.parametrize('change', ['source_sha256', 'source_job_id', 'nan', 'reference_disagreement'])
def test_bad_transcript_is_rejected_before_creating_child(revision_case, change):
    from clipping.revisions import revise_clip
    case = revision_case
    data = json.loads(case['corrected'].read_text())
    if change in ('source_sha256', 'source_job_id'):
        data[change] = 'changed'
    elif change == 'nan':
        data['segments'][0]['start'] = float('nan')
    else:
        data['segments'][0]['text'] = 'Entirely unrelated invented speech about something completely different.'
    case['corrected'].write_text(json.dumps(data))
    with pytest.raises(ValueError):
        revise_clip(case['storage'], case['parent'], case['corrected'])
    assert len(case['engine'].list()) == 1


def test_stale_order_change_during_review_cannot_install_or_commit(revision_case, monkeypatch):
    from clipping.revisions import revise_clip
    case = revision_case
    def concurrent(*args):
        state = case['store'].get_order(case['controller'].state['id'])
        state['external_note'] = 'concurrent writer'
        case['store'].save_order(state)
        return {'passed': True}
    monkeypatch.setattr(orchestrator, 'verify_export', concurrent)
    with pytest.raises(ValueError, match='revision_changed'):
        revise_clip(case['storage'], case['parent'], case['corrected'])
    assert case['store'].get_clip(case['parent'])['status'] == 'READY'
    assert not list(case['delivery'].glob('*.mp4'))


def test_existing_revision_filename_is_not_overwritten(revision_case):
    from clipping.revisions import revise_clip
    case = revision_case
    case['delivery'].mkdir()
    target = case['delivery'] / 'old-01-r1.mp4'
    target.write_bytes(b'operator file')
    with pytest.raises(ValueError, match='existing_delivery_changed'):
        revise_clip(case['storage'], case['parent'], case['corrected'])
    assert target.read_bytes() == b'operator file' and len(case['store'].list_clips()) == 1


def test_targeted_consumer_does_not_take_an_earlier_unrelated_job(revision_case):
    case = revision_case
    engine = case['engine']
    unrelated = engine.create(engine.get(case['parent'])['payload'], 'earlier')
    assert engine.consume_once(job_id='missing-job') is False
    assert engine.get(unrelated['id'])['status'] == 'queued'


def test_database_commit_failure_removes_only_new_revision_delivery(revision_case, monkeypatch):
    from clipping import revisions
    case = revision_case
    case['delivery'].mkdir()
    original = case['delivery'] / 'old-01.mp4'
    original.write_bytes(b'original delivery remains')
    def fail(*args):
        raise ValueError('transaction failure')
    monkeypatch.setattr(revisions, '_commit', fail)
    with pytest.raises(ValueError, match='transaction failure'):
        revisions.revise_clip(case['storage'], case['parent'], case['corrected'])
    assert list(case['delivery'].iterdir()) == [original]
    assert original.read_bytes() == b'original delivery remains'
    assert case['store'].get_clip(case['parent'])['status'] == 'READY'


def test_reviewed_niche_and_post_caption_apply_to_child_only(revision_case):
    from clipping.revisions import revise_clip
    case = revision_case
    result = revise_clip(case['storage'], case['parent'], case['corrected'],
        post_caption='New separate post caption.',
        niche_review={'niche': 'ai-technology', 'rationale': 'An editor reviewed the AI discussion.'})
    assert Path(result['clip']).parent == case['delivery'] / 'ai-technology'
    assert case['store'].get_clip(result['clip_id'])['caption'] == 'New separate post caption.'
    assert case['store'].get_clip(case['parent'])['caption'] == 'A separate post caption.'
    assert case['engine'].get(case['parent'])['payload']['caption'] == 'A separate post caption.'


def test_recovery_audits_current_revision_and_retains_superseded_history(revision_case):
    from clipping.recovery import recover_order
    from clipping.revisions import revise_clip
    case = revision_case
    child = revise_clip(case['storage'], case['parent'], case['corrected'])
    report = recover_order(case['storage'], case['controller'].state['id'])
    assert [item['clip_id'] for item in report['clips']] == [child['clip_id']]
    assert report['blocked_count'] == 0 and len(case['store'].list_clips()) == 2


def test_batch_resume_preserves_revision_path_provenance_and_parent(revision_case, monkeypatch):
    from clipping import batch, production
    from clipping.revisions import revise_clip
    case = revision_case
    original = case['delivery'] / 'old-01.mp4'
    case['delivery'].mkdir()
    original.write_bytes(b'original delivery')
    corrected = revise_clip(case['storage'], case['parent'], case['corrected'],
        niche_review={'niche': 'ai-technology', 'rationale': 'Reviewed AI discussion.'})
    controller = case['controller']
    controller.state, controller._revision = case['store'].read_order(controller.state['id'])
    controller.engine = case['engine']
    controller.update(batch_results=[], completed_clip_count=0)
    entry = controller.state['clip_entries'][0]
    monkeypatch.setattr(production, 'metadata_for', lambda *args: entry['source'])
    batch.deliver_clip(controller, case['engine'].get(corrected['clip_id']), entry,
                       entry['moment'], case['delivery'])
    saved = case['store'].get_clip(corrected['clip_id'])
    assert saved['path'] == corrected['clip']
    assert saved['settings']['caption_revision'] == corrected['caption_revision']
    assert controller.state['batch_results'][0]['caption_revision'] == corrected['caption_revision']
    assert original.read_bytes() == b'original delivery'
    assert not list(case['delivery'].glob('*source123*'))
    again = revise_clip(case['storage'], case['parent'], case['corrected'],
        niche_review={'niche': 'ai-technology', 'rationale': 'Reviewed AI discussion.'})
    assert again['status'] == 'already_revised'
