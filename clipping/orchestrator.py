"""One-order controller for discovery, clipping, captions and export review."""

import argparse
import importlib.util
import json
import os
import shutil
import ssl
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from clipping import media, trends
from clipping.template import CAPTION_STYLES, DEFAULT_CAPTION_STYLE, DEFAULT_FRAMING_MODE
from clipping.workflow import ClippingWorkflow


class ConnectionIssue(Exception):
    def __init__(self, code):
        self.code = code


class SetupIssue(Exception):
    def __init__(self, code):
        self.code = code


class OrderBusy(Exception):
    pass


@dataclass
class Config:
    provider: str = 'selenium'
    browser_python: str | None = None
    niche: str | None = None
    caption_style: str = DEFAULT_CAPTION_STYLE
    duration: int = 35
    framing_mode: str = DEFAULT_FRAMING_MODE
    # Defaults keep historical saved orders compatible. The CLI creates partial batches.
    clip_count: int = 1
    partial_downloads: bool = False
    delivery_dir: str | None = None
    caption_styles: list[str] | None = None
    clips_per_source: int = 4

    def validate(self):
        if self.provider not in ('selenium', 'public'):
            raise ValueError('Choose selenium or public discovery')
        if self.caption_style not in CAPTION_STYLES:
            raise ValueError('Choose a supported caption style')
        if self.framing_mode not in ('fit', 'crop'):
            raise ValueError('Choose fit or crop framing')
        if isinstance(self.duration, bool) or not isinstance(self.duration, int) or not 15 <= self.duration <= 60:
            raise ValueError('Choose a clip duration from 15 to 60 seconds')
        if self.niche is not None and self.niche not in [item['name'] for item in trends.NICHES]:
            raise ValueError('Choose a configured search niche')
        if self.browser_python is not None and not isinstance(self.browser_python, str):
            raise ValueError('Browser Python must be an executable path')
        if (not isinstance(self.partial_downloads, bool) or isinstance(self.clip_count, bool)
                or not isinstance(self.clip_count, int)):
            raise TypeError('Invalid partial-download settings')
        if self.clip_count < 1 or not self.partial_downloads and self.clip_count != 1:
            raise ValueError('Choose a positive clip count; multiple clips require partial downloads')
        if (isinstance(self.clips_per_source, bool) or not isinstance(self.clips_per_source, int)
                or not 1 <= self.clips_per_source <= 20):
            raise ValueError('Choose one to 20 moments per source')
        if self.delivery_dir is not None and not isinstance(self.delivery_dir, str):
            raise ValueError('Delivery folder must be a path')
        if self.caption_styles is not None:
            if (not isinstance(self.caption_styles, list) or not 1 <= len(self.caption_styles) <= 4
                    or any(style not in CAPTION_STYLES for style in self.caption_styles)):
                raise ValueError('Choose one to four supported caption styles')
            if not self.partial_downloads:
                raise ValueError('Multiple caption styles require a partial-download batch')


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def order_lock(folder):
    with (folder / 'controller.lock').open('a+b') as handle:
        handle.write(b'0')
        handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise OrderBusy() from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def check_environment(config, storage):
    for executable in ('ffmpeg', 'ffprobe'):
        if not shutil.which(executable):
            raise SetupIssue(executable + '_missing')
    for name in ('yt_dlp', 'yt_dlp_ejs', 'faster_whisper'):
        if not importlib.util.find_spec(name):
            raise SetupIssue(name + '_missing')
    if not (shutil.which('node') or shutil.which('deno')):
        raise SetupIssue('javascript_runtime_missing')
    model = Path(media.whisper_model_location(storage, 'en'))
    if not media.model_files_ready(model):
        raise SetupIssue('local_speech_model_missing')
    os.environ['CLIPPING_DISCOVERY_PROVIDER'] = 'selenium' if config.provider == 'selenium' else ''
    if config.provider == 'selenium':
        interpreter = config.browser_python or shutil.which('python')
        if not interpreter or not Path(interpreter).is_file():
            raise SetupIssue('selenium_python_missing')
        os.environ['CLIPPING_SELENIUM_PYTHON'] = str(Path(interpreter).resolve())


def check_browser(config):
    if config.provider != 'selenium':
        try:
            with urlopen(Request('https://www.youtube.com/robots.txt', method='HEAD'), timeout=10):
                return
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise ConnectionIssue('youtube_temporarily_unavailable') from exc
            return  # An HTTP response proves connectivity; discovery checks actual source access.
        except URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise SetupIssue('youtube_tls_verification_failed') from exc
            raise ConnectionIssue('youtube_connection_unavailable') from exc
        except (TimeoutError, OSError) as exc:
            raise ConnectionIssue('youtube_connection_unavailable') from exc
        return
    try:
        response = json.loads(media.command([os.environ['CLIPPING_SELENIUM_PYTHON'],
            str(Path(__file__).with_name('youtube_browser.py')), '--check'], timeout=70, kill_tree=True))
    except subprocess.TimeoutExpired as exc:
        raise ConnectionIssue('browser_check_timeout') from exc
    except (ValueError, KeyError, OSError) as exc:
        raise SetupIssue('browser_check_failed') from exc
    if response.get('status') == 'source_unavailable':
        raise ConnectionIssue(response.get('reason') or 'youtube_connection_unavailable')
    if response.get('status') != 'ok':
        raise SetupIssue(response.get('reason') or 'browser_setup_failed')


def verify_export(engine, job, folder):
    from clipping.clip_review import verify_export as review
    return review(engine, job, folder)


class Controller:
    def __init__(self, storage, config=None, *, resume=None, emit=None, sleeper=time.sleep):
        self.storage = Path(storage).resolve()
        self.orders = self.storage / 'orders'
        self.orders.mkdir(parents=True, exist_ok=True)
        self.emit = emit or (lambda value: print(json.dumps(value, ensure_ascii=True), flush=True))
        self.sleeper = sleeper
        self.mutex = threading.RLock()
        self.engine = None
        if resume is not None:
            identifier = json.loads((self.orders / 'latest.json').read_text())['id'] if resume == 'latest' else resume
            try:
                identifier = str(uuid.UUID(identifier))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError('Invalid saved order identifier') from exc
            self.folder = self.orders / identifier
            self.manifest = self.folder / 'order.json'
            if self.manifest.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('Saved order is too large')
            self.state = json.loads(self.manifest.read_text(encoding='utf-8'))
            if self.state.get('id') != identifier:
                raise ValueError('Saved order identifier does not match its folder')
            self.config = Config(**self.state['config'])
        else:
            self.config = config or Config()
            self.config.validate()
            identifier = str(uuid.uuid4())
            self.folder = self.orders / identifier
            self.folder.mkdir()
            self.manifest = self.folder / 'order.json'
            self.state = {'id': identifier, 'created_at': timestamp(), 'status': 'created',
                          'stage': 'preflight', 'config': asdict(self.config), 'connection_failures': 0,
                          'resume_command': 'run-youtube-clipping.cmd --resume ' + identifier}
            atomic_json(self.manifest, self.state)
            atomic_json(self.orders / 'latest.json', {'id': identifier})
        self.config.validate()

    def update(self, **values):
        with self.mutex:
            self.state.update(values, updated_at=timestamp())
            atomic_json(self.manifest, self.state)
            message = {'order_id': self.state['id'], 'status': self.state['status'],
                       'stage': self.state['stage'], **values}
            with (self.folder / 'events.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(message, ensure_ascii=True) + '\n')
            if self.config.partial_downloads:
                large_fields = {'moments', 'clip_entries', 'batch_results', 'result', 'review', 'source_selection',
                                'source_reports', 'skipped_entries'}
                concise = {key: value for key, value in message.items() if key not in large_fields}
                if values.get('result'):
                    concise['clips'] = [clip['clip'] for clip in values['result']['clips']]
                self.emit(concise)
            else:
                self.emit(message)

    def connected(self, action, stage, attempts, delay):
        for attempt in range(attempts):
            self.update(status='running', stage=stage, reason=None, next_attempt_at=None,
                        retry_in_seconds=None, attempt=attempt + 1, connection_attempt_limit=attempts)
            try:
                return action()
            except ConnectionIssue:
                self.state['connection_failures'] += 1
                if attempt + 1 == attempts:
                    raise
                seconds = min(60, delay * 2 ** attempt)
                self.update(status='retry_wait', stage=stage,
                            next_attempt_at=(datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
                            retry_in_seconds=seconds, attempt=attempt + 1)
                self.sleeper(seconds)

    def search(self, research):
        if not self.state.get('research_run_id'):
            scan = research.request_scan()
            self.update(research_run_id=scan['id'])
        scan = research.get(self.state['research_run_id'])
        if scan['status'] in ('retry_scheduled', 'running'):
            # The order lock proves that no other controller owns this private DB.
            research._save(scan, 'queued')  # This isolated order follows the controller's bounded backoff.
        if scan['status'] not in ('completed', 'partial'):
            research.consume_once()
        scan = research.get(self.state['research_run_id'])
        if scan['status'] == 'retry_scheduled':
            raise ConnectionIssue('youtube_search_unavailable')
        if scan['status'] == 'failed':
            raise SetupIssue('youtube_search_failed')
        if not any(source.get('eligible_preview') for source in scan['results']):
            raise SetupIssue('no_eligible_sources')
        return scan

    def prepare(self):
        job_id = self.state['job_id']
        job = self.engine.get(job_id)
        if job['status'] in ('retry_scheduled', 'awaiting_transcript'):
            self.engine._save(job_id, job['output'], 'queued', job['current_step'], expected=job['status'])
        elif job['status'] in ('failed', 'blocked'):
            self.engine.retry(job_id)
        finished = threading.Event()

        def monitor():
            last, last_update = None, time.monotonic()
            while not finished.wait(.5):
                current = self.engine.get(job_id)
                self.engine.heartbeat()
                if current['current_step'] != last or time.monotonic() - last_update >= 15:
                    last, last_update = current['current_step'], time.monotonic()
                    self.update(stage=last, status='running')

        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        try:
            self.engine.consume_once()
        finally:
            finished.set()
            watcher.join(2)
        job = self.engine.get(job_id)
        if job['status'] == 'retry_scheduled':
            raise ConnectionIssue('source_download_connection_unavailable')
        return job

    def finish(self, job):
        self.update(status='running', stage='export_review', result=None, review=None)
        (self.folder / 'result.json').unlink(missing_ok=True)
        review = verify_export(self.engine, job, self.folder)
        output = job['output']
        result = {'order_id': self.state['id'], 'job_id': job['id'],
                  'clip': str(self.engine.artifact(job['id'], 'clip')),
                  'subtitles': str(self.engine.artifact(job['id'], 'subtitles')),
                  'source': output.get('source_selection'),
                  'clip_plan': output.get('selected_clip_plan'),
                  'selection_note': output.get('planning_note'),
                  'post_caption': output.get('caption', ''), 'caption_style': self.config.caption_style,
                  'review': review}
        (self.folder / 'post-caption.txt').write_text(result['post_caption'], encoding='utf-8')
        atomic_json(self.folder / 'result.json', result)
        self.update(status='ready_for_review', stage='finished', result=result, review=review,
                    action='Review the saved clip, captions and source context.',
                    reason=None, next_attempt_at=None)
        return self.state

    def run(self, connection_attempts=3, retry_delay=5):
        if not 1 <= connection_attempts <= 10 or not 0 <= retry_delay <= 300:
            raise ValueError('Invalid connection retry policy')
        try:
            with order_lock(self.folder):
                try:
                    return self.execute(connection_attempts, retry_delay)
                except ConnectionIssue as exc:
                    self.update(status='connection_unavailable', reason=exc.code,
                                next_attempt_at=None, action='Check connectivity in the normal terminal and resume this saved order.')
                except SetupIssue as exc:
                    action = ('Run the resume command in a normal terminal; Chrome could not create a browser session here.'
                              if exc.code in ('browser_execution_refused', 'browser_session_not_created', 'driver_or_browser_unavailable')
                              else 'Correct the reported setup or search settings, then resume the order.')
                    self.update(status='no_sources' if exc.code in ('no_eligible_sources', 'no_accessible_sources') else 'setup_required',
                                reason=exc.code, action=action)
                except KeyboardInterrupt:
                    if self.engine and self.state.get('job_id'):
                        job = self.engine.get(self.state['job_id'])
                        if job['status'] == 'running':
                            self.engine._save(job['id'], job['output'], 'queued', job['current_step'],
                                              error='Controller interrupted')
                    self.update(status='interrupted', reason='operator_interrupted', action='Resume this saved order.')
                except Exception:  # noqa: BLE001 - redact untrusted worker exceptions at the CLI boundary.
                    self.update(status='quality_failed' if self.state['stage'] == 'export_review' else 'failed',
                                reason='stage_failed', action='Inspect the saved stage and correct it before resuming.')
        except OrderBusy:
            return {**self.state, 'status': 'already_running', 'reason': 'saved_order_in_use'}
        return self.state

    def execute(self, attempts, delay):
        if self.config.partial_downloads and self.config.clip_count > 4:
            from clipping.production import execute_production
            return execute_production(self, attempts, delay)
        if self.config.partial_downloads:
            from clipping.batch import execute_batch
            return execute_batch(self, attempts, delay)
        atomic_json(self.orders / 'latest.json', {'id': self.state['id']})
        self.engine = ClippingWorkflow(self.folder / 'workflow.db', self.storage)
        if self.state.get('job_id'):
            interrupted = self.engine.get(self.state['job_id'])
            if interrupted['status'] == 'running':
                self.engine._save(interrupted['id'], interrupted['output'], 'queued',
                                  interrupted['current_step'], error='Recovered interrupted controller')
        if self.state.get('job_id') and self.engine.get(self.state['job_id'])['status'] == 'completed':
            return self.finish(self.engine.get(self.state['job_id']))
        self.update(status='running', stage='preflight', action=None)
        check_environment(self.config, self.storage)
        niches = [item for item in trends.NICHES if not self.config.niche or item['name'] == self.config.niche]
        research = trends.TrendResearchAgent(self.engine, niches=niches)
        scan = None
        if not self.state.get('job_id'):
            self.connected(lambda: check_browser(self.config), 'source_connectivity', attempts, delay)
            scan = self.connected(lambda: self.search(research), 'youtube_search', attempts, delay)
            self.update(stage='source_selection', sources_found=len(scan['results']), search_status=scan['status'])
        while True:
            if not self.state.get('job_id'):
                scan = scan or research.get(self.state['research_run_id'])
                rejected = self.state.get('rejected_sources', [])
                choices = [source for source in scan['results'] if source.get('eligible_preview')
                           and source['id'] not in rejected]
                if len(rejected) >= 3 or not choices:
                    raise SetupIssue('no_accessible_sources')
                job = research.preview(scan['id'], choices[0]['id'], caption_style=self.config.caption_style,
                                       target_duration=self.config.duration, framing_mode=self.config.framing_mode)
                self.update(job_id=job['id'], source_id=job['payload']['source_selection']['id'])
            current = self.engine.get(self.state['job_id'])
            job = current if current['output'].get('failure_code') == 'source_access_required' else self.connected(
                self.prepare, 'prepare_clip', attempts, delay)
            if job['status'] == 'completed':
                return self.finish(job)
            if job['output'].get('failure_code') == 'source_access_required':
                self.update(stage='source_selection', job_id=None,
                            rejected_sources=list(dict.fromkeys(self.state.get('rejected_sources', [])
                                                               + [self.state['source_id']])))
                continue
            self.update(status='transcript_required' if job['status'] == 'awaiting_transcript' else 'failed',
                        stage=job['current_step'], reason='speech_transcript_required' if job['status'] == 'awaiting_transcript'
                        else 'clip_preparation_failed', action='Correct the saved processing stage and resume this order.')
            return self.state


def main(argv=None):
    parser = argparse.ArgumentParser(description='Search YouTube and make captioned highlights using only selected video windows.')
    parser.add_argument('--resume', nargs='?', const='latest', help='Resume a saved order ID (default: latest)')
    parser.add_argument('--new', action='store_true', help='Start a new order and fresh search (the default)')
    parser.add_argument('--status', action='store_true', help='Show saved state without running workers')
    parser.add_argument('--provider', choices=('selenium', 'public'))
    parser.add_argument('--browser-python', help='Python executable containing Selenium')
    parser.add_argument('--niche', choices=[item['name'] for item in trends.NICHES])
    styles = parser.add_mutually_exclusive_group()
    styles.add_argument('--caption-style', choices=CAPTION_STYLES)
    styles.add_argument('--caption-styles', nargs='+', choices=CAPTION_STYLES,
                        help='Rotate these styles across the clips in this order')
    parser.add_argument('--clips', type=int, help='Positive clip count; larger runs use multiple sources (default: 4)')
    parser.add_argument('--per-source', type=int, help='Maximum moments per source in larger runs (1 to 20; default: 4)')
    parser.add_argument('--output', type=Path, help='One flat delivery folder (default: project clips folder)')
    parser.add_argument('--duration', type=int, help='Target duration, 15 to 60 seconds (default: 35)')
    parser.add_argument('--framing', choices=('fit', 'crop'), help='Fit preserves the full source over a blurred background')
    parser.add_argument('--connection-attempts', type=int, default=3)
    parser.add_argument('--retry-delay', type=int, default=5, help='Initial backoff seconds; doubles up to 60 seconds')
    parser.add_argument('--storage', type=Path, default=Path(__file__).resolve().parents[1] / 'storage/clipping')
    options = parser.parse_args(argv)
    if options.new and (options.resume or options.status):
        parser.error('Choose a new order or a saved order')
    if not 1 <= options.connection_attempts <= 10 or not 0 <= options.retry_delay <= 300:
        parser.error('Connection attempts must be 1 to 10; retry delay must be 0 to 300 seconds')
    if (options.resume or options.status) and any(value is not None for value in
            (options.provider, options.niche, options.caption_style, options.duration, options.framing,
             options.clips, options.output, options.caption_styles, options.per_source)):
        parser.error('Resume uses saved source and caption settings. Start a new order to change them.')
    try:
        config = Config(provider=options.provider or 'selenium', browser_python=options.browser_python,
                        niche=options.niche, caption_style=options.caption_style or DEFAULT_CAPTION_STYLE,
                        duration=options.duration if options.duration is not None else 35,
                        framing_mode=options.framing or DEFAULT_FRAMING_MODE,
                        clip_count=options.clips if options.clips is not None else 4,
                        partial_downloads=True,
                        delivery_dir=str(options.output.resolve()) if options.output else None,
                        caption_styles=options.caption_styles,
                        clips_per_source=options.per_source if options.per_source is not None else 4)
        controller = Controller(options.storage, config, resume=options.resume or ('latest' if options.status else None))
        if options.status:
            print(json.dumps(controller.state, ensure_ascii=True))
            return 0
        if options.browser_python:
            controller.config.browser_python = options.browser_python
            controller.state['config'] = asdict(controller.config)
        state = controller.run(options.connection_attempts, options.retry_delay)
        summary = {key: state.get(key) for key in ('id', 'status', 'stage', 'reason', 'resume_command',
                                                  'requested_clip_count', 'completed_clip_count', 'partial_index')}
        if state['status'] == 'ready_for_review':
            if controller.config.partial_downloads:
                summary.update(clips=[{key: clip[key] for key in ('number', 'clip', 'caption_style', 'post_caption', 'selection_note')}
                                      for clip in state['result']['clips']],
                               delivery_dir=state['result']['delivery_dir'], index=state['result'].get('index'),
                               human_review_required=True)
            else:
                summary.update(clip=state['result']['clip'], post_caption=state['result']['post_caption'],
                               human_review_required=True)
        print(json.dumps(summary, ensure_ascii=True), flush=True)
        return {'ready_for_review': 0, 'connection_unavailable': 75, 'interrupted': 130,
                'already_running': 3}.get(state['status'], 2)
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'status': 'setup_required', 'reason': 'invalid_configuration_or_saved_order',
                          'action': 'Check the arguments and saved order path. Use --help for supported options.'}))
        return 2


if __name__ == '__main__':
    # Batch helpers import this module. Use its canonical classes at the CLI too,
    # so their typed setup/connection exceptions match the controller's handlers.
    from clipping.orchestrator import main as cli_main
    raise SystemExit(cli_main())
