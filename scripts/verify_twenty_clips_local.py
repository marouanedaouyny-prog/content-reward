"""Exercise twenty real exports using an explicitly cached local test source.

Run with the project's .venv Python. The default only prepares and validates
the fixture; --run enables real Whisper, FFmpeg rendering and export review.
No network access, source discovery or publishing is performed by this test.
It is not evidence of a fresh YouTube production run or editorial approval.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from clipping import media, orchestrator, production, sections  # noqa: E402


CACHE = PROJECT / '.workflow-tests/orchestrator-native-e2973a8114934db6aee394b5f9658a4c/media'
SOURCE_ID = 'Q-DFC0AnbY4'
SOURCE_HASH = 'c288492b4669e2e61a3c583ecd6bf5a3c0919c76fbfaa87fdd4f5df3b1b7a058'
TRANSCRIPT_HASH = '7ce1ff75e5e72e6b7b472bdddba4e23050477266faec96479e223ed6776caf58'
FIXTURE_DATE = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


class FixtureClock(datetime):
    """Only the production eligibility check uses this declared fixture clock."""

    @classmethod
    def now(cls, tz=None):
        return FIXTURE_DATE.astimezone(tz) if tz else FIXTURE_DATE.replace(tzinfo=None)


def save(path, value):
    orchestrator.atomic_json(path, value)


def event(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def prepare(root):
    source_path, transcript_path = CACHE / 'source.mp4', CACHE / 'transcript.json'
    if media.file_hash(source_path) != SOURCE_HASH or media.file_hash(transcript_path) != TRANSCRIPT_HASH:
        raise ValueError('Cached source/transcript differs from the verified fixture')
    transcript = json.loads(transcript_path.read_text(encoding='utf-8'))
    info = media.probe(source_path)
    duration = float(info['format']['duration'])
    metadata = {'id': SOURCE_ID, 'title': '[LOCAL CACHED TEST] Dana White interview',
                'duration': duration, 'segments': transcript['segments'], 'heatmap': [],
                'transcript_origin': 'cached_faster_whisper_fixture_not_public_discovery'}
    moments = sections.select_moments(metadata, 20, 15, strict=True)
    if len(moments) != 20:
        raise ValueError('The real cached transcript does not contain twenty eligible fixture windows')
    model = PROJECT / 'storage/clipping/models/tiny.en'
    if not media.model_files_ready(model):
        raise ValueError('The existing local English speech model is unavailable')
    source = {'id': SOURCE_ID, 'url': f'https://www.youtube.com/watch?v={SOURCE_ID}',
              'title': metadata['title'], 'creator': 'The Diary Of A CEO', 'duration': duration,
              'published_at': '2026-10-05T00:00:00+00:00', 'eligible_preview': True,
              'views': None, 'observed_at': None, 'niches': ['Business'],
              'acquisition_mode': 'local_cached_test_fixture', 'live_discovery_verified': False}
    fixture = {'test_only': True, 'fresh_youtube_run': False, 'source_path': str(source_path),
               'source_sha256': SOURCE_HASH, 'transcript_path': str(transcript_path),
               'transcript_sha256': TRANSCRIPT_HASH, 'source': source,
               'eligibility_fixture_clock': FIXTURE_DATE.isoformat(),
               'model_path': str(model), 'planned_count': len(moments),
               'total_planned_clip_seconds': round(sum(m['clip_plan']['duration_seconds'] for m in moments), 3),
               'new_full_source_downloads': 0, 'moments': moments}
    save(root / 'fixture.json', fixture)
    return fixture, metadata


def run(root, fixture, metadata, interrupt_after):
    storage, delivery = root / 'storage', root / 'delivery'
    ledger_path = root / 'acquisitions.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.is_file() else []
    source_path = Path(fixture['source_path'])
    marker = root / 'interruption-injected.json'
    config = orchestrator.Config(provider='public', clip_count=20, clips_per_source=20,
        partial_downloads=True, caption_style='colorized', duration=15,
        framing_mode='fit', delivery_dir=str(delivery))
    latest = storage / 'orders/latest.json'
    controller = orchestrator.Controller(storage, config, resume='latest' if latest.is_file() else None)

    def fixture_scan(current, attempts, delay):
        current.update(research_run_id='local-cache-fixture-no-live-search',
                       discovery_fixture=True, live_discovery_verified=False)
        return {'results': [fixture['source']], 'status': 'completed',
                'provider': 'explicit_local_cache_test_adapter'}

    def inspect(source, folder):
        if source['id'] != SOURCE_ID:
            raise ValueError('Unexpected local fixture source')
        return metadata

    def acquire(source, plan, duration, folder):
        if (interrupt_after and controller.state.get('completed_clip_count', 0) >= interrupt_after
                and not marker.is_file()):
            save(marker, {'completed_clip_count': controller.state['completed_clip_count'],
                          'purpose': 'Deliberate fixture interruption to prove resume'})
            raise media.SourceUnavailable('Deliberate local-test interruption; no network request occurred')
        if source['id'] != SOURCE_ID or duration != metadata['duration']:
            raise ValueError('Unexpected source in the bounded local adapter')
        start, length = plan['start_seconds'], plan['duration_seconds']
        if not 15 <= length <= 60 or start < 0 or start + length > duration + .15:
            raise ValueError('Invalid bounded local fixture window')
        begin, end = max(0, start - 3), min(duration, start + length + 3)
        folder.mkdir(parents=True, exist_ok=True)
        path, checkpoint = folder / 'section.mp4', folder / 'fixture-acquisition.json'
        identity = {'source_id': SOURCE_ID, 'clip_plan': plan, 'source_sha256': SOURCE_HASH}
        reused = False
        if path.is_file() and checkpoint.is_file():
            old = json.loads(checkpoint.read_text(encoding='utf-8'))
            reused = old.get('identity') == identity and old.get('sha256') == media.file_hash(path)
        if not reused:
            media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-ss', str(begin), '-i', str(source_path), '-t', str(end - begin),
                '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'ultrafast',
                '-crf', '18', '-threads', '2', '-c:a', 'aac', '-b:a', '128k', str(path)],
                timeout=180, kill_tree=True)
            save(checkpoint, {'identity': identity, 'sha256': media.file_hash(path)})
            ledger.append({'source_id': SOURCE_ID, 'source_clip_plan': plan,
                           'bounded_start': begin, 'bounded_end': end, 'path': str(path),
                           'sha256': media.file_hash(path), 'method': 'local_ffmpeg_bounded_extraction'})
            save(ledger_path, ledger)
        section_duration = sections._validate_section(path, end - begin, start - begin + length)
        return {'path': path, 'source_offset': begin, 'local_start': start - begin,
                'requested_end': end, 'duration': section_duration, 'sha256': media.file_hash(path)}

    def render_forbidden(*args, **kwargs):
        raise AssertionError('Completed fixture exports must not render again on resume')

    started = time.monotonic()
    with patch.dict(os.environ, {'WHISPER_MODEL': fixture['model_path']}), \
            patch.object(production, 'scan_sources', fixture_scan), \
            patch.object(production, 'datetime', FixtureClock), \
            patch.object(sections, 'inspect_source', inspect), \
            patch.object(sections, 'download_section', acquire):
        state = controller.run(connection_attempts=1, retry_delay=0)
        if state['status'] == 'connection_unavailable' and marker.is_file():
            before = {clip['job_id']: media.file_hash(Path(clip['clip'])) for clip in state['batch_results']}
            save(root / 'interrupted-state.json', {'order_id': state['id'],
                'completed_clip_count': state['completed_clip_count'], 'export_hashes': before})
            if len(before) != interrupt_after:
                raise AssertionError('The deliberate interruption did not preserve the expected count')
            controller = orchestrator.Controller(storage, resume=state['id'])
            state = controller.run(connection_attempts=1, retry_delay=0)
            if state['status'] == 'ready_for_review':
                after = {clip['job_id']: media.file_hash(Path(clip['clip'])) for clip in state['result']['clips']}
                if any(after.get(job_id) != checksum for job_id, checksum in before.items()):
                    raise AssertionError('Resume changed an already completed export')
        if state['status'] != 'ready_for_review':
            save(root / 'incomplete-state.json', state)
            raise ValueError(f'Local fixture did not finish: {state["status"]} at {state["stage"]}')
        first_hashes = {clip['job_id']: media.file_hash(Path(clip['clip'])) for clip in state['result']['clips']}
        # A second completed-order resume must reverify artifacts without any ASR,
        # rendering or bounded extraction work.
        with patch.object(media, 'render', render_forbidden), \
                patch.object(media, 'transcribe', render_forbidden), \
                patch.object(sections, 'download_section', render_forbidden):
            resumed = orchestrator.Controller(storage, resume=state['id'])
            state = resumed.run(connection_attempts=1, retry_delay=0)
        if state['status'] != 'ready_for_review':
            raise AssertionError('A completed fixture order failed its real export recheck')
    clips = state['result']['clips']
    if len(clips) != 20 or len(first_hashes) != 20 or len(set(first_hashes.values())) != 20:
        raise AssertionError('Expected twenty distinct real exports and jobs')
    windows = sorted((c['source_clip_plan']['start_seconds'],
                      c['source_clip_plan']['start_seconds'] + c['source_clip_plan']['duration_seconds'])
                     for c in clips)
    if any(previous[1] + 3 > current[0] for previous, current in zip(windows, windows[1:])):
        raise AssertionError('Fixture windows overlap or violate their three-second separation')
    for clip in clips:
        if clip['caption_style'] != 'colorized' or clip['framing_mode'] != 'fit':
            raise AssertionError('Fixture export does not use the requested visual settings')
        if not all(clip['review']['checks'].values()):
            raise AssertionError('An actual export failed the shared mechanical verifier')
        if (not clip['review']['checks'].get('spoken_caption_coverage')
                or not (clip['review'].get('caption_assessment') or {}).get('passed')):
            raise AssertionError('The real export did not pass independent source-caption coverage review')
        job = resumed.engine.get(clip['job_id'])
        if (not job['payload'].get('source_reference') or job['payload'].get('transcription_hint')
                or not job['output'].get('caption_assessment', {}).get('passed')):
            raise AssertionError('The real transcription did not use the corrected source-caption gate')
        styled = Path(clip['clip']).with_suffix('.ass')
        if not styled.is_file() or '6BFF7C' not in styled.read_text(encoding='utf-8'):
            raise AssertionError('The delivered colorized ASS subtitle artifact is missing')
    if len(ledger) < 20 or len(list(delivery.glob('*.mp4'))) != 20:
        raise AssertionError('Expected at least twenty bounded acquisitions and exactly twenty delivered MP4s')
    if media.file_hash(source_path) != SOURCE_HASH:
        raise AssertionError('The original cached source changed')
    audit = {'test_only': True, 'fresh_youtube_run': False, 'live_discovery_verified': False,
             'order_id': state['id'], 'status': state['status'], 'clip_count': len(clips),
             'unique_job_count': len(first_hashes), 'unique_clip_hash_count': len(set(first_hashes.values())),
             'bounded_acquisition_count': len(ledger), 'new_full_source_downloads': 0,
             'real_whisper_transcription': True, 'real_ffmpeg_render_and_verification': True,
             'source_caption_coverage_verified': True,
             'completed_resume_did_not_regenerate': True,
             'interruption_resume_tested': marker.is_file(), 'source_hash': SOURCE_HASH,
             'rejected_entries': state.get('skipped_entries', []),
             'elapsed_seconds': round(time.monotonic() - started, 3),
             'delivery_dir': str(delivery), 'result': state['result'],
             'human_review_required': True, 'speech_accuracy': 'not_verified',
             'limit': 'Cached source and fixture discovery prove local orchestration; live acquisition and editorial quality remain separate.'}
    save(root / 'audit.json', audit)
    event({key: value for key, value in audit.items() if key not in ('result', 'rejected_entries')})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Render and verify the real twenty-export local fixture')
    parser.add_argument('--workdir', type=Path, help='Resume an existing isolated .workflow-tests/twenty-local-* folder')
    parser.add_argument('--interrupt-after', type=int, default=9,
                        help='Inject one recoverable interruption after this many exports; zero disables it')
    options = parser.parse_args(argv)
    if not 0 <= options.interrupt_after < 20:
        parser.error('Interruption count must be zero through nineteen')
    if os.environ.get('DRY_RUN', '').lower() in ('true', '1', 'yes'):
        parser.error('This test requires actual media; DRY_RUN is enabled in this process')
    base = (PROJECT / '.workflow-tests').resolve()
    root = options.workdir.resolve() if options.workdir else base / f'twenty-local-{uuid.uuid4().hex}'
    if root.parent != base or not root.name.startswith('twenty-local-'):
        parser.error('Workdir must be an isolated .workflow-tests/twenty-local-* folder')
    root.mkdir(parents=True, exist_ok=True)
    fixture, metadata = prepare(root)
    event({'status': 'fixture_ready', 'workdir': str(root), 'planned_count': fixture['planned_count'],
           'planned_seconds': fixture['total_planned_clip_seconds'], 'test_only': True,
           'fresh_youtube_run': False, 'render_enabled': options.run})
    if options.run:
        run(root, fixture, metadata, options.interrupt_after)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
