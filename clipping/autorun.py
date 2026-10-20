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
    return {'id': state['id'], 'mode': mode, 'status': state['status'],
            'stage': state['stage'], 'reason': state.get('reason'),
            'requested_clip_count': controller.config.clip_count,
            'completed_clip_count': state.get('completed_clip_count', len(clips)),
            'clips': [clip['clip'] for clip in clips],
            'index': result.get('index') or state.get('partial_index'),
            'manifest': str(controller.manifest),
            'events': str(controller.folder / 'events.jsonl'),
            'resume_command': f'run-clipping-auto.cmd --resume {state["id"]}',
            'action': state.get('action'), 'human_review_required': True}


def execute(options):
    pointer = options.storage / 'orders/latest.json'
    saved = options.resume or ('latest' if pointer.is_file() and not options.new else None)
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
                     'provider': options.provider, 'delivery_dir': output}
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
                        delivery_dir=output)
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
