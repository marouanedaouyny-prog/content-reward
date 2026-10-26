"""Noninteractive clipping entry point for chat-triggered runs."""

import argparse
import json
from pathlib import Path

from app.core.errors import PipelineError

from clipping import trends
from clipping.orchestrator import Config, Controller, OrderBusy, order_lock


DEFAULT_STORAGE = Path(__file__).resolve().parents[1] / 'storage/clipping'
FINISHED = {'ready_for_review', 'completed', 'cancelled'}


def summary(controller, mode, state=None):
    state = state if state is not None else controller.state
    result = state.get('result') or {}
    clips = result.get('clips') or state.get('batch_results') or []
    from clipping.library import delivery_availability
    records = {clip['id']: clip for clip in controller.store.list_clips(state['id'])}
    available, missing = [], []
    for clip in clips:
        record = records.get(clip.get('job_id'), {})
        hashes = dict(record.get('settings', {}).get('delivery_hashes') or {})
        if record.get('sha256'):
            hashes['video'] = record['sha256']
        availability = delivery_availability(clip.get('clip'), clip.get('subtitles'), expected_hashes=hashes)
        if availability['available']:
            available.append(clip['clip'])
        else:
            missing.append({'number': clip.get('number'), **availability})
    unavailable = bool(missing) and state['status'] in {'ready_for_review', 'completed'}
    index = result.get('index') or state.get('partial_index')
    diagnostic = state.get('source_failure')
    if isinstance(diagnostic, dict):
        from clipping.media import SourceFailure
        diagnostic = SourceFailure('', reason=diagnostic.get('reason'),
            http_status=diagnostic.get('http_status'), timeout_seconds=diagnostic.get('timeout_seconds')).diagnostic
    else:
        diagnostic = None
    return {'id': state['id'], 'mode': mode,
            'status': 'delivery_unavailable' if unavailable else state['status'],
            'recorded_status': state['status'],
            'stage': state['stage'], 'reason': state.get('reason'),
            'requested_clip_count': controller.config.clip_count,
            'completed_clip_count': state.get('completed_clip_count', len(clips)),
            'available_clip_count': len(available), 'missing_artifacts': missing,
            'clips': available,
            'index': index if index and Path(index).is_file() else None,
            'manifest': str(controller.manifest),
            'events': str(controller.folder / 'events.jsonl'),
            'resume_command': f'run-clipping-auto.cmd --resume {state["id"]}',
            'action': ('Delivery files are missing. Resume this saved order to recheck retained jobs and restore exports.'
                       if unavailable else state.get('action')),
            'source_failure': diagnostic, 'human_review_required': True}


def execute(options):
    from app.repositories.store import Store
    database = options.storage / 'content-reward.db'
    orders = options.storage / 'orders'
    context_path = getattr(options, 'learning_context', None)
    context = None
    if context_path is not None:
        from analytics.models import MeasurementContext
        if context_path.stat().st_size > 8192:
            raise ValueError('Learning context must be a small local JSON file')
        context = MeasurementContext.model_validate_json(context_path.read_text(encoding='utf-8')).model_dump(mode='json')
    if options.status and not database.exists() and not orders.exists():
        return {'status': 'not_started', 'mode': 'status', 'clips': [], 'index': None}, 0
    store = Store(options.storage / 'content-reward.db')
    store.import_orders(options.storage / 'orders', lock_factory=order_lock)
    latest = store.latest_order()
    if not latest and not options.new and ((orders / 'latest.json').is_file()
                                         or any(orders.glob('*/order.json')) or store.import_warnings()):
        raise ValueError('Historical orders need recovery before a new batch')
    saved = options.resume or ('latest' if latest and not options.new else None)
    controller = Controller(options.storage, resume=saved) if saved else None
    if options.status:
        return (summary(controller, 'status') if controller else
                {'status': 'not_started', 'mode': 'status', 'clips': [], 'index': None}), 0
    resume = controller is not None and (options.resume or (
        controller.config.partial_downloads and controller.config.clip_count > 4
        and controller.state['status'] not in FINISHED))
    output = str(options.output.resolve()) if options.output else None
    if resume:
        overrides = {'clip_count': options.clips, 'niche': options.niche,
                     'provider': options.provider, 'delivery_dir': output, 'campaign_id': options.campaign,
                     'measurement_context': context}
        if any(value is not None and value != getattr(controller.config, key)
               for key, value in overrides.items()):
            return {**summary(controller, 'resumed'), 'status': 'setup_required',
                    'reason': 'pending_order_settings_conflict',
                    'action': 'Omit changed settings to resume, or use --new for a separate order.'}, 2
    else:
        from app.core.config import load_settings
        settings = load_settings()
        config = Config(provider=options.provider or 'public', niche=options.niche,
                        clip_count=options.clips if options.clips is not None else settings.clips.target_count,
                        clips_per_source=settings.production.clips_per_source, partial_downloads=True,
                        caption_style=settings.production.caption_style,
                        framing_mode=settings.video.framing, duration=settings.clips.target_duration,
                        delivery_dir=output, campaign_id=options.campaign, organize_by_niche=True,
                        measurement_context=context)
        controller = Controller(options.storage, config)
    state = controller.run(options.connection_attempts, options.retry_delay)
    report = summary(controller, 'resumed' if resume else 'new', state)
    if state['status'] == 'already_running':
        report['action'] = 'The saved order is already running. Use --status to read its progress.'
    return report, {'ready_for_review': 0, 'connection_unavailable': 75,
                    'interrupted': 130, 'already_running': 3}.get(state['status'], 2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--new', action='store_true', help='Start a fresh batch instead of resuming')
    modes.add_argument('--status', action='store_true', help='Read saved status without running workers')
    modes.add_argument('--resume', nargs='?', const='latest', help='Resume an exact order ID or latest')
    parser.add_argument('--clips', type=int, help='New-run target (default: 20)')
    parser.add_argument('--niche', choices=[niche['name'] for niche in trends.NICHES])
    parser.add_argument('--campaign', help='Saved campaign ID; its rules gate preparation')
    parser.add_argument('--learning-context', type=Path, help='Local JSON describing the account, reporting window and metric definitions')
    parser.add_argument('--provider', choices=('public', 'selenium'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--storage', type=Path, default=DEFAULT_STORAGE)
    parser.add_argument('--connection-attempts', type=int, default=3)
    parser.add_argument('--retry-delay', type=int, default=5)
    options = parser.parse_args(argv)
    if options.clips is not None and options.clips < 1:
        parser.error('The clip target must be positive')
    if not 1 <= options.connection_attempts <= 10 or not 0 <= options.retry_delay <= 300:
        parser.error('Connection attempts must be 1 to 10; retry delay must be 0 to 300 seconds')
    try:
        if options.status:
            report, code = execute(options)
        else:
            folder = options.storage / 'autorun'
            folder.mkdir(parents=True, exist_ok=True)
            with order_lock(folder):
                report, code = execute(options)
    except OrderBusy:
        report, code = {'status': 'already_running', 'reason': 'automatic_runner_in_use',
                        'action': 'An automatic run is active. Use --status to read its progress.'}, 3
    except (ValueError, OSError, KeyError, TypeError, PipelineError):
        report, code = {'status': 'setup_required', 'reason': 'invalid_configuration_or_saved_order',
                        'action': 'Check the saved order and arguments; use --help for supported options.'}, 2
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
