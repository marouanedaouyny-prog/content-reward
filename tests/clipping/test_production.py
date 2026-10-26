"""Production orchestration with explicit fixture boundaries for external/media IO."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


TOPICS = [
    ('Customers buy outcomes.', 'Demonstrate the result before asking them to pay.'),
    ('Hiring begins with a clear role.', 'List the required skills before scheduling interviews.'),
    ('Cash flow keeps a company alive.', 'Keep reserves for taxes and supplier payments.'),
    ('Useful meetings produce decisions.', 'Assign an owner and deadline to each action.'),
    ('Good sleep starts before bedtime.', 'Reduce evening light and keep a consistent schedule.'),
    ('Strength grows during recovery.', 'Leave enough rest between demanding training sessions.'),
    ('A warmup prepares the movement.', 'Practice the exercise with a lighter weight first.'),
    ('Walking is easy to repeat.', 'Attach a short walk to your regular lunch break.'),
    ('Evaluation starts with realistic examples.', 'Measure model mistakes on actual customer questions.'),
    ('Backups need restoration practice.', 'Recover a sample database before an incident happens.'),
    ('Passwords should be unique.', 'Use a password manager to avoid repeating credentials.'),
    ('Latency changes how software feels.', 'Measure the slowest interactions before optimizing them.'),
    ('A goalkeeper reads body position.', 'Watch the hips before committing to a direction.'),
    ('A team needs a shared plan.', 'Agree on a small number of signals before the match.'),
    ('Distance runners build gradually.', 'Increase training volume without sacrificing recovery days.'),
    ('An athlete can practice composure.', 'Use a familiar breathing routine before competition.'),
    ('A joke needs a clear setup.', 'Remove details that distract from the final surprise.'),
    ('Improvisation depends on listening.', 'Respond to the offer your partner actually makes.'),
    ('An interview improves with curiosity.', 'Follow the unexpected answer instead of reading ahead.'),
    ('Stage fright becomes manageable.', 'Rehearse the first minute until it feels familiar.'),
    ('Players learn from useful feedback.', 'Explain a failed action before asking them to retry.'),
    ('A tutorial should teach one mechanic.', 'Let the player practice before introducing another rule.'),
    ('Difficulty needs a steady curve.', 'Compare completion rates before changing a game level.'),
    ('Small prototypes expose weak ideas.', 'Test the central interaction before producing expensive art.'),
]


def pipeline(tmp_path, monkeypatch, count=20):
    from clipping import media, orchestrator, sections, trends
    calls = {'search': 0, 'inspect': 0, 'cache': 0, 'download': 0, 'render': 0, 'review': 0}
    monkeypatch.setattr(orchestrator, 'check_environment', lambda *args: None)
    monkeypatch.setattr(orchestrator, 'check_browser', lambda *args: None)

    def discover(niche):
        calls['search'] += 1
        return [{'id': f'source{i:05}', 'title': 'Practical ideas and clear examples',
                 'uploader': f'Fixture creator {i}', 'view_count': 500000 - i * 1000,
                 'duration': 1800, 'timestamp': datetime.now(timezone.utc).timestamp() - 86400}
                for i in range(6)]

    def inspect(source, folder, **kwargs):
        calls['inspect'] += 1
        calls['cache'] += kwargs.get('cache') is not None
        index = int(source['id'][-5:])
        segments = []
        for i, (opening, payoff) in enumerate(TOPICS[index * 4:index * 4 + 4]):
            start = 100 + i * 100
            segments += [{'start': start, 'end': start + 10, 'text': opening},
                         {'start': start + 10, 'end': start + 35, 'text': payoff}]
        return {'id': source['id'], 'title': source['title'], 'duration': 1800,
                'segments': segments, 'heatmap': [], 'transcript_origin': 'fixture_public_captions'}

    def download(source, plan, duration, folder, **kwargs):
        calls['download'] += 1
        assert 15 <= plan['duration_seconds'] <= 60
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'section.mp4'
        path.write_bytes(f'BOUNDED FIXTURE {source["id"]} {plan["start_seconds"]}'.encode())
        return {'path': path, 'source_offset': plan['start_seconds'] - 3, 'local_start': 3,
                'duration': plan['duration_seconds'] + 6, 'sha256': media.file_hash(path)}

    def ingest(data, output, folder, storage):
        assert data['preview_only'] is True and data['dry_run'] is False
        assert data['source_path'] and not data.get('source_url')
        assert data['source_reference'] and not data.get('transcription_hint')
        return {'source_path': data['source_path'], 'source_sha256': media.file_hash(storage / data['source_path']),
                'source_duration': 41, 'synthetic_source': False}

    def transcribe(data, output, folder, storage):
        path = folder / 'transcript.json'
        path.write_text(json.dumps({'segments': [{'start': 3, 'end': 38, 'text': 'A complete fixture thought.'}]}))
        return {'transcript_path': path.relative_to(storage).as_posix(), 'transcript_origin': 'faster_whisper:fixture'}

    def render(data, output, folder, storage):
        calls['render'] += 1
        assert data['caption_style'] == 'colorized' and data['framing_mode'] == 'fit'
        clip, subs = folder / 'clip.mp4', folder / 'subtitles.srt'
        clip.write_bytes(('EXPORT FIXTURE ' + data['source_path']).encode())
        subs.write_text('1\n00:00:00,000 --> 00:00:35,000\nA complete fixture thought.\n')
        return {'clip_path': clip.relative_to(storage).as_posix(), 'clip_sha256': media.file_hash(clip),
                'subtitle_path': subs.relative_to(storage).as_posix()}

    def review(engine, job, folder):
        calls['review'] += 1
        assert media.file_hash(engine.artifact(job['id'], 'clip')) == job['output']['clip_sha256']
        return {'checks': {'fixture_hash': True}, 'frames': [], 'human_review_required': True}

    monkeypatch.setattr(trends, 'discover', discover)
    monkeypatch.setattr(sections, 'inspect_source', inspect)
    monkeypatch.setattr(sections, 'download_section', download)
    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(media, 'transcribe', transcribe)
    monkeypatch.setattr(media, 'render', render)
    monkeypatch.setattr(orchestrator, 'verify_export', review)
    config = orchestrator.Config(provider='public', clip_count=count, partial_downloads=True,
                                 caption_style='colorized', delivery_dir=str(tmp_path / 'delivered'))
    return orchestrator, config, calls


def test_twenty_clips_use_five_sources_and_resume_without_regenerating(tmp_path, monkeypatch):
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review', state
    clips = state['result']['clips']
    assert len(clips) == len({c['job_id'] for c in clips}) == 20
    assert len({c['source']['id'] for c in clips}) == 5
    assert len({(c['source']['id'], c['source_clip_plan']['start_seconds']) for c in clips}) == 20
    assert all(c['caption_style'] == 'colorized' for c in clips)
    assert state['result']['full_video_downloaded'] is False
    assert calls['search'] == len(mod.trends.NICHES) and calls['download'] == calls['render'] == 20
    assert calls['cache'] == calls['inspect']
    assert Path(state['result']['index']).is_file()
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert resumed.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert calls['search'] == len(mod.trends.NICHES) and calls['download'] == calls['render'] == 20


def test_failed_candidate_is_skipped_and_replaced_without_stopping_order(tmp_path, monkeypatch):
    from clipping import batch
    from clipping.orchestrator import SetupIssue
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    original = batch.create_clip_job
    rejected = []

    def reject_one(controller, entry, moment, metadata, attempts, delay):
        if not rejected:
            rejected.append(moment['source_excerpt'])
            raise SetupIssue('candidate_quality_failed')
        return original(controller, entry, moment, metadata, attempts, delay)

    monkeypatch.setattr(batch, 'create_clip_job', reject_one)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review', state
    assert state['completed_clip_count'] == 20
    assert calls['download'] == calls['render'] == 20
    assert len(state['skipped_entries']) == 1
    assert state['skipped_entries'][0]['skip_reason'] == 'candidate_quality_failed'
    clips = state['result']['clips']
    assert len({(c['source']['id'], c['source_clip_plan']['start_seconds']) for c in clips}) == 20


def test_larger_requested_count_has_no_twenty_clip_ceiling(tmp_path, monkeypatch):
    mod, config, calls = pipeline(tmp_path, monkeypatch, count=24)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review'
    assert len(state['result']['clips']) == calls['render'] == 24


def test_poor_automatic_captions_are_replaced_without_padding_the_count(tmp_path, monkeypatch):
    from clipping import media
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    original = media.transcribe
    failed = []

    def incomplete(*args):
        if not failed:
            failed.append(True)
            raise media.TranscriptRequired('Automatic caption coverage failed')
        return original(*args)

    monkeypatch.setattr(media, 'transcribe', incomplete)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review', state
    assert len(state['result']['clips']) == 20
    assert len(state['skipped_entries']) == 1
    assert [clip['number'] for clip in state['result']['clips']] == list(range(1, 21))


@pytest.mark.parametrize('count', [5, 6])
def test_failed_caption_window_can_be_replaced_from_the_same_source(tmp_path, monkeypatch, count):
    from clipping import media, sections, trends
    mod, config, calls = pipeline(tmp_path, monkeypatch, count=count)
    config.clips_per_source = 5
    discover, inspect, transcribe = trends.discover, sections.inspect_source, media.transcribe
    monkeypatch.setattr(trends, 'discover', lambda niche: discover(niche)[:1 if count == 5 else 2])

    def more_moments(source, folder, **kwargs):
        metadata = inspect(source, folder, **kwargs)
        for index, (opening, payoff) in enumerate(TOPICS[4:8], start=4):
            start = 100 + index * 100
            metadata['segments'] += [{'start': start, 'end': start + 10, 'text': opening},
                                     {'start': start + 10, 'end': start + 35, 'text': payoff}]
        return metadata

    failures = []

    def poor_once(*args):
        if not failures:
            failures.append(True)
            raise media.TranscriptRequired('Automatic caption coverage failed')
        return transcribe(*args)

    monkeypatch.setattr(sections, 'inspect_source', more_moments)
    monkeypatch.setattr(media, 'transcribe', poor_once)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review', state
    clips = state['result']['clips']
    assert len(clips) == count and calls['download'] == count + 1
    source_counts = [sum(clip['source']['id'] == source_id for clip in clips)
                     for source_id in {clip['source']['id'] for clip in clips}]
    assert max(source_counts) == 5
    assert len(source_counts) == (1 if count == 5 else 2)
    assert len({(clip['source']['id'], clip['source_clip_plan']['start_seconds']) for clip in clips}) == count


def test_repeated_caption_failures_stop_retrying_an_unsuitable_source(tmp_path, monkeypatch):
    from clipping import media
    mod, config, calls = pipeline(tmp_path, monkeypatch)

    def incomplete(*args):
        raise media.TranscriptRequired('Automatic caption coverage failed')

    monkeypatch.setattr(media, 'transcribe', incomplete)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'insufficient_sources' and state['completed_clip_count'] == 0
    assert calls['download'] == 18 and calls['render'] == 0
    assert {report['outcome'] for report in state['source_reports']} == {'captions_unusable'}


def test_connection_failure_after_nine_exports_resumes_in_same_order(tmp_path, monkeypatch):
    from clipping import media, sections
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    original = sections.download_section

    def interrupted(*args, **kwargs):
        if calls['download'] == 9:
            raise media.SourceUnavailable('Connection refused SECRET')
        return original(*args, **kwargs)

    monkeypatch.setattr(sections, 'download_section', interrupted)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'connection_unavailable'
    assert state['completed_clip_count'] == 9 and not state.get('result')
    assert not (controller.folder / 'result.json').exists()
    monkeypatch.setattr(sections, 'download_section', original)
    resumed = mod.Controller(tmp_path, resume=state['id'], emit=lambda _: None)
    result = resumed.run(connection_attempts=1)
    assert result['id'] == state['id'] and result['status'] == 'ready_for_review'
    assert calls['render'] == calls['download'] == 20
    assert calls['search'] == len(mod.trends.NICHES) and 'SECRET' not in resumed.manifest.read_text()


def test_production_routes_new_exports_into_the_chosen_niche_folder(tmp_path, monkeypatch):
    mod, config, calls = pipeline(tmp_path, monkeypatch, count=5)
    config.niche = 'Business'
    config.organize_by_niche = True
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review', state
    assert {Path(clip['clip']).parent for clip in state['result']['clips']} == {tmp_path / 'delivered' / 'business'}
    assert all(clip['delivery_niche'] == 'business' for clip in state['result']['clips'])
    from clipping.library import niche_library
    category = next(item for item in niche_library(controller.store)['categories'] if item['id'] == 'business')
    assert category['available_clip_count'] == category['clip_count'] == 5
    before = calls['download']
    resumed = mod.Controller(tmp_path, resume=state['id'], emit=lambda _: None)
    assert resumed.run(connection_attempts=1)['status'] == 'ready_for_review'
    assert calls['download'] == before


@pytest.mark.parametrize('count', [4, 5])
def test_failed_resume_preflight_preserves_completed_partial_deliveries(tmp_path, monkeypatch, count):
    from clipping import media, sections
    mod, config, calls = pipeline(tmp_path, monkeypatch, count=count)
    original = sections.download_section

    def interrupted(*args, **kwargs):
        if calls['download'] == 2:
            raise media.SourceUnavailable('Connection unavailable')
        return original(*args, **kwargs)

    monkeypatch.setattr(sections, 'download_section', interrupted)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['completed_clip_count'] == 2
    completed = list(state['batch_results'])

    def broken_environment(*args):
        raise mod.SetupIssue('ffmpeg_section_seek_unsupported')

    monkeypatch.setattr(mod, 'check_environment', broken_environment)
    resumed = mod.Controller(tmp_path, resume=state['id'], emit=lambda _: None)
    failed = resumed.run(connection_attempts=1)
    assert failed['status'] == 'setup_required'
    assert failed['completed_clip_count'] == 2
    assert failed['batch_results'] == completed
    assert all(Path(clip['clip']).is_file() for clip in failed['batch_results'])


def test_unavailable_source_does_not_limit_twenty_clip_order_to_three_candidates(tmp_path, monkeypatch):
    from clipping import media, sections
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    original = sections.inspect_source

    def inaccessible(source, folder, **kwargs):
        if source['id'] == 'source00000':
            raise media.SourceAccessRequired('Source refused SECRET')
        return original(source, folder, **kwargs)

    monkeypatch.setattr(sections, 'inspect_source', inaccessible)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review'
    assert len(state['result']['clips']) == 20
    assert 'source00000' not in {c['source']['id'] for c in state['result']['clips']}
    assert 'SECRET' not in controller.manifest.read_text()


def test_next_fresh_order_excludes_previous_windows_and_reports_shortfall(tmp_path, monkeypatch):
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    first = mod.Controller(tmp_path, config, emit=lambda _: None)
    old = first.run(connection_attempts=1)
    assert old['status'] == 'ready_for_review'
    old_windows = {(c['source']['id'], c['source_clip_plan']['start_seconds']) for c in old['result']['clips']}
    second = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = second.run(connection_attempts=1)
    assert state['status'] == 'insufficient_sources'
    assert state['id'] != first.state['id'] and calls['search'] == 2 * len(mod.trends.NICHES)
    assert state['completed_clip_count'] == 4 and not state.get('result')
    new_windows = {(c['source']['id'], c['source_clip_plan']['start_seconds']) for c in state['batch_results']}
    assert not old_windows & new_windows


def test_caption_inspection_rechecks_actual_long_source_duration(tmp_path, monkeypatch):
    from clipping import sections
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    original = sections.inspect_source

    def misleading_duration(source, folder, **kwargs):
        metadata = original(source, folder, **kwargs)
        if source['id'] == 'source00000':
            metadata['duration'] = 7300
        return metadata

    monkeypatch.setattr(sections, 'inspect_source', misleading_duration)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review'
    assert 'source00000' not in {clip['source']['id'] for clip in state['result']['clips']}


def test_replacement_source_cannot_reuse_the_previous_sources_cached_section(tmp_path, monkeypatch):
    from clipping import media, sections
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    original = sections.download_section

    def leaves_cache(source, plan, duration, folder, **kwargs):
        cached = folder / 'section.mp4'
        if cached.is_file():
            assert source['id'] in cached.read_text(), 'Wrong source reused from the section cache'
        result = original(source, plan, duration, folder, **kwargs)
        if source['id'] == 'source00000':
            raise media.SourceAccessRequired('Refused after leaving a cached section')
        return result

    monkeypatch.setattr(sections, 'download_section', leaves_cache)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review', state
    assert len(state['result']['clips']) == 20
    assert 'source00000' not in {clip['source']['id'] for clip in state['result']['clips']}


def test_failed_recheck_removes_ready_manifest_and_index(tmp_path, monkeypatch):
    mod, config, calls = pipeline(tmp_path, monkeypatch)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    index = Path(state['result']['index'])
    controller.engine.artifact(state['result']['clips'][0]['job_id'], 'clip').write_bytes(b'CHANGED')
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    result = resumed.run(connection_attempts=1)
    assert result['status'] == 'quality_failed' and not result.get('result')
    assert not index.exists() and not (resumed.folder / 'result.json').exists()
    assert not (tmp_path / 'delivered' / 'LATEST-CLIPS.txt').exists()
    assert not (tmp_path / 'delivered' / f'{result["id"][:8]}-result.json').exists()
    assert calls['render'] == 20


@pytest.mark.parametrize('stale_excerpt', [
    'Yes, sir. I agree. We should do a fight at the White House.',
    'I believed I could be successful when I was younger, but let me tell you what.',
])
def test_completed_production_resume_rechecks_current_candidate_before_redelivery(tmp_path, monkeypatch, stale_excerpt):
    mod, config, calls = pipeline(tmp_path, monkeypatch, count=5)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review'
    entries = json.loads(json.dumps(state['clip_entries']))
    completed = {entry['job_id']: controller.engine.get(entry['job_id']) for entry in entries}
    assert all(job['status'] == 'completed' for job in completed.values())
    missing_delivery = Path(state['result']['clips'][0]['clip'])
    missing_delivery.unlink()
    entries[0]['moment']['source_excerpt'] = stale_excerpt
    assert entries[0]['moment']['quality']['completed_ending'] is True
    assert entries[0]['moment']['quality']['filler_opening'] is False
    controller.update(clip_entries=entries)
    before_calls = calls.copy()

    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    result = resumed.run(connection_attempts=1)

    assert result['status'] == 'setup_required' and result['reason'] == 'candidate_quality_failed'
    assert result.get('result') is None and result['batch_results'] == []
    assert not missing_delivery.exists()
    assert calls == before_calls, 'A rejected completed moment must not reach full review, acquisition or rendering'
    assert result['clip_entries'] == entries
    assert {identifier: resumed.engine.get(identifier) for identifier in completed} == completed


def test_production_creation_rejects_saved_intro_before_acquisition(tmp_path, monkeypatch):
    from clipping import batch, production
    mod, config, calls = pipeline(tmp_path, monkeypatch, count=5)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review'
    entry = state['clip_entries'][0]
    before_entry = json.loads(json.dumps(entry))
    before_job = controller.engine.get(entry['job_id'])
    metadata = production.metadata_for(controller, entry)
    start = entry['source_clip_plan']['start_seconds']
    metadata['chapters'] = [{'title': 'Intro', 'start_time': start + 5, 'end_time': start + 10}]
    before_calls = calls.copy()
    with pytest.raises(mod.SetupIssue) as rejected:
        batch.create_clip_job(controller, entry, entry['moment'], metadata, 1, 0)
    assert rejected.value.code == 'candidate_chapter_excluded'
    assert calls == before_calls and entry == before_entry
    assert controller.engine.get(entry['job_id']) == before_job


@pytest.mark.parametrize('blocked', [True, False])
def test_completed_production_resume_checks_chapters_in_source_coordinates(tmp_path, monkeypatch, blocked):
    mod, config, calls = pipeline(tmp_path, monkeypatch, count=5)
    controller = mod.Controller(tmp_path, config, emit=lambda _: None)
    state = controller.run(connection_attempts=1)
    assert state['status'] == 'ready_for_review'
    entries = json.loads(json.dumps(state['clip_entries']))
    first = entries[0]
    before_jobs = {entry['job_id']: controller.engine.get(entry['job_id']) for entry in entries}
    metadata_path = controller.folder / first['metadata_path']
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    start = first['source_clip_plan']['start_seconds']
    assert first['local_clip_plan']['start_seconds'] == 3 and start >= 100
    metadata['chapters'] = [{'title': 'Intro', 'start_time': start + 5 if blocked else 0,
                             'end_time': start + 10 if blocked else 50}]
    metadata_path.write_text(json.dumps(metadata), encoding='utf-8')
    missing = Path(state['result']['clips'][0]['clip'])
    missing.unlink()
    before_calls = calls.copy()
    resumed = mod.Controller(tmp_path, resume='latest', emit=lambda _: None)
    result = resumed.run(connection_attempts=1)
    if blocked:
        assert result['status'] == 'setup_required' and result['reason'] == 'candidate_chapter_excluded'
        assert not missing.exists() and calls == before_calls
    else:
        assert result['status'] == 'ready_for_review' and missing.is_file()
        assert calls['download'] == before_calls['download'] and calls['render'] == before_calls['render']
    assert result['clip_entries'] == entries
    assert {identifier: resumed.engine.get(identifier) for identifier in before_jobs} == before_jobs


@pytest.mark.parametrize('count', [0, -1, True, 1.5])
def test_invalid_clip_counts_are_rejected(count):
    from clipping.orchestrator import Config
    with pytest.raises((TypeError, ValueError)):
        Config(clip_count=count, partial_downloads=True).validate()


def test_large_positive_target_and_per_source_settings_validate():
    from clipping.orchestrator import Config
    Config(clip_count=10000, partial_downloads=True, clips_per_source=4).validate()
    for value in (0, 21, True, 1.5):
        with pytest.raises((TypeError, ValueError)):
            Config(clip_count=20, partial_downloads=True, clips_per_source=value).validate()
