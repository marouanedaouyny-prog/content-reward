"""Canonical local Content Reward commands, with no implicit publication."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from app.core.config import load_settings
from app.core.errors import PipelineError


def print_json(value):
    print(json.dumps(value, ensure_ascii=True, indent=2, default=str))


def _niche(value):
    """Accept a configured niche name or free text and return a search niche."""
    from clipping import trends
    for item in trends.NICHES:
        if item['name'].casefold() == str(value or '').casefold():
            return dict(item)
    name = str(value or '').strip() or 'Business'
    return {'name': name, 'query': name}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='content-reward', description=__doc__)
    parser.add_argument('--storage', type=Path)
    commands = parser.add_subparsers(dest='command')
    for name in ('run', 'resume', 'status', 'recover', 'revise', 'worker', 'api', 'clips', 'library', 'campaigns', 'validate', 'metrics', 'prepare', 'smoke', 'discover', 'discovery-health', 'social'):
        command = commands.add_parser(name)
        command.add_argument('--storage', type=Path, default=argparse.SUPPRESS)
        if name == 'social':
            command.add_argument('action', choices=['status'], default='status', nargs='?')
        if name == 'run':
            command.add_argument('--target', '--clips', type=int)
            command.add_argument('--new', action='store_true')
            command.add_argument('--niche')
            command.add_argument('--provider', choices=['public', 'selenium'])
            command.add_argument('--campaign')
            command.add_argument('--learning-context', type=Path)
        if name in ('resume', 'status'):
            command.add_argument('order', nargs='?')
        if name == 'recover':
            command.add_argument('order')
            command.add_argument('--restore', action='store_true', help='Restore passing retained exports without acquisition')
            command.add_argument('--organize', action='store_true', help='Also create niche-folder copies; requires --restore')
        if name == 'revise':
            command.add_argument('clip_id')
            command.add_argument('--transcript', type=Path, required=True)
            command.add_argument('--post-caption')
            command.add_argument('--niche-review', type=Path)
        if name == 'worker':
            command.add_argument('--once', action='store_true')
        if name == 'api':
            command.add_argument('--host', default='127.0.0.1')
            command.add_argument('--port', type=int, default=8000)
        if name in ('clips', 'campaigns'):
            command.add_argument('action', choices=['list', 'import'] if name == 'campaigns' else ['list'], default='list', nargs='?')
            if name == 'campaigns':
                command.add_argument('file', type=Path, nargs='?')
        if name == 'metrics':
            command.add_argument('action', choices=['report', 'import'], default='report', nargs='?')
            command.add_argument('file', type=Path, nargs='?')
        if name in ('validate', 'prepare'):
            command.add_argument('clip_id')
        if name == 'discover':
            command.add_argument('--niche', default='Business')
            command.add_argument('--mode', choices=['fast', 'balanced', 'deep'], default='balanced')
            command.add_argument('--no-cache', action='store_true')
            command.add_argument('--dry-run', action='store_true')
            command.add_argument('--debug', action='store_true')
            command.add_argument('--region')
            command.add_argument('--language')
        if name == 'discovery-health':
            command.add_argument('--history', action='store_true')
        if name == 'prepare':
            command.add_argument('--campaign', required=True)
            command.add_argument('--platform', choices=['youtube', 'instagram', 'tiktok'], required=True)
            command.add_argument('--caption', required=True)
            command.add_argument('--title', default='')
            command.add_argument('--key', required=True)
    options = parser.parse_args(argv)
    if options.command is None:
        parser.print_help()
        return 0
    try:
        if options.command == 'social':
            from clipping.social_bridge import main as social_status
            return social_status()
        settings = load_settings()
        storage = options.storage or Path(settings.paths.storage)
        if options.command in ('run', 'resume', 'status'):
            from clipping.autorun import main as automatic
            args = ['--storage', str(storage)]
            if options.command == 'run':
                if options.new:
                    args += ['--new']
                for option, name in [('target', 'clips'), ('niche', 'niche'), ('provider', 'provider'),
                                     ('campaign', 'campaign'), ('learning_context', 'learning-context')]:
                    if getattr(options, option) is not None:
                        args += ['--' + name, str(getattr(options, option))]
            else:
                if options.command == 'status':
                    args += ['--status']
                if options.command == 'resume' or options.order:
                    args += ['--resume', options.order or 'latest']
            return automatic(args)
        if options.command == 'api':
            from clipping.__main__ import main as api
            previous_storage = os.environ.get('CLIPPING_STORAGE')
            try:
                os.environ['CLIPPING_STORAGE'] = str(storage)
                return api(['--host', options.host, '--port', str(options.port)]) or 0
            finally:
                if previous_storage is None:
                    os.environ.pop('CLIPPING_STORAGE', None)
                else:
                    os.environ['CLIPPING_STORAGE'] = previous_storage
        if options.command == 'smoke':
            from scripts.smoke_test import main as smoke
            return smoke(['--storage', str(storage)])
        if options.command == 'recover':
            from clipping.recovery import recover_order
            from clipping.orchestrator import OrderBusy
            try:
                report = recover_order(storage, options.order, restore=options.restore, organize=options.organize)
            except OrderBusy:
                print_json({'status': 'already_running', 'action': 'Wait for this saved order to release its lock.'})
                return 3
            print_json(report)
            return 2 if report['blocked_count'] else 0
        if options.command == 'revise':
            from clipping.revisions import revise_clip
            from clipping.orchestrator import OrderBusy
            niche_review = None
            if options.niche_review is not None:
                if options.niche_review.stat().st_size > 8192:
                    raise ValueError('Niche review must be smaller than 8 KB')
                niche_review = json.loads(options.niche_review.read_text(encoding='utf-8-sig'))
            try:
                report = revise_clip(storage, options.clip_id, options.transcript,
                    post_caption=options.post_caption, niche_review=niche_review)
            except OrderBusy:
                print_json({'status': 'already_running', 'action': 'Wait for this saved order to release its lock.'})
                return 3
            print_json(report)
            return 0
        if options.command in ('discover', 'discovery-health'):
            from clipping.discovery import service
            if options.command == 'discovery-health':
                report = service.health(storage)
                if options.history:
                    report['history'] = service.source_history(storage)
                print_json(report)
                return 0
            niche = _niche(options.niche)
            outcome = service.discover(niche, storage=storage, mode=options.mode,
                                       region=options.region, language=options.language,
                                       use_cache=not options.no_cache, dry_run=options.dry_run,
                                       debug=options.debug, settings=settings)
            payload = {'run_id': outcome.run_id, 'niche': outcome.niche, 'mode': outcome.mode,
                       'tier': outcome.tier, 'queries': outcome.queries,
                       'providers': outcome.providers,
                       'sources': [{'id': item.id, 'title': item.title, 'url': item.url,
                                    'duration_seconds': item.duration_seconds, 'views': item.views,
                                    'channel': item.channel, 'provider': item.provider,
                                    'providers_seen': item.providers_seen}
                                   for item in outcome.sources],
                       'diagnostics': outcome.diagnostics, 'error': outcome.error,
                       'clips_started': False}
            print_json(payload)
            return 0 if outcome.ok else 2
        if options.command == 'worker':
            from clipping.workflow import ClippingWorkflow
            engine = ClippingWorkflow(settings.paths.database, storage)
            engine.recover_interrupted()
            try:
                while True:
                    consumed = engine.consume_once()
                    if options.once:
                        print_json({'consumed': consumed})
                        return 0
                    if not consumed:
                        time.sleep(.5)
            except KeyboardInterrupt:
                engine.shutdown_requested = True
                return 130
        from app.repositories.store import Store
        store = Store(storage / 'content-reward.db')
        if options.command == 'library':
            from clipping.library import niche_library
            print_json(niche_library(store))
        elif options.command == 'clips':
            from clipping.library import clip_availability
            print_json([dict(id=c['id'], path=c['path'], status=c['status'],
                            **clip_availability(c)) for c in store.list_clips()])
        elif options.command == 'campaigns':
            if options.action == 'import':
                from campaigns.models import Campaign
                if options.file is None or options.file.stat().st_size > 128000:
                    raise ValueError('Supply a campaign JSON file smaller than 128 KB')
                store.save_campaign(Campaign.model_validate_json(options.file.read_text(encoding='utf-8')))
            print_json([c.model_dump(mode='json') for c in store.list_campaigns()])
        elif options.command == 'metrics':
            if options.action == 'import':
                from analytics.collectors import collect_performance
                from analytics.models import ClipPerformance
                if options.file is None or options.file.stat().st_size > 128000:
                    raise ValueError('Supply an observation JSON file smaller than 128 KB')
                collect_performance(store, ClipPerformance.model_validate_json(options.file.read_text(encoding='utf-8')))
            from analytics.reports import business_metrics
            print_json(business_metrics(store))
        elif options.command == 'prepare':
            from publishing.manager import PublishingManager
            print_json(PublishingManager(store, output=Path(settings.paths.output) / 'prepared').publish(
                options.clip_id, dict(caption=options.caption, title=options.title), campaign_id=options.campaign,
                platform=options.platform, key=options.key))
        elif options.command == 'validate':
            from clipping.quality.validation import validate_media
            from clipping.media import file_hash
            clip = store.get_clip(options.clip_id)
            plan = clip['settings']['source_clip_plan']
            report = validate_media(Path(clip['path']), Path(clip['subtitles']), duration=plan['duration_seconds'],
                                    aspect=plan.get('aspect_ratio', '9:16'))
            if Path(clip['path']).is_file() and file_hash(Path(clip['path'])) != clip['sha256']:
                report.passed = False
                report.checks['recorded_hash'] = False
                report.violations.append('recorded_hash')
            print_json(report.model_dump())
            return 0 if report.passed else 2
        return 0
    except PipelineError as error:
        print_json(error.as_dict())
        return 2
    except (ValueError, OSError, KeyError, TypeError):
        print_json({'code': 'VALIDATION_ERROR', 'message': 'Check the command, supplied local file and saved IDs.'})
        return 2


if __name__ == '__main__':
    sys.exit(main())
