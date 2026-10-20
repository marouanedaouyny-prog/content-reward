"""Repeatable, resumable runs of distinct highlights across fresh long sources."""

import json
import math
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clipping import batch, clip_history, media, orchestrator, sections, trends
from clipping.orchestrator import OrderBusy, SetupIssue, atomic_json, order_lock
from clipping.workflow import ClippingWorkflow


def metadata_for(controller, entry):
    path = (controller.folder / entry['metadata_path']).resolve()
    if not path.is_relative_to(controller.folder) or path.stat().st_size > 8_000_000:
        raise ValueError('Invalid source metadata path')
    metadata = json.loads(path.read_text(encoding='utf-8'))
    if metadata['id'] != entry['source']['id']:
        raise ValueError('Source metadata does not match the selected highlight')
    return metadata


def current_reservations(entries, order_id):
    return [{'source_id': entry['source']['id'], 'clip_plan': entry['moment']['clip_plan'],
             'source_excerpt': entry['moment']['source_excerpt'], 'order_id': order_id}
            for entry in entries]


def scan_sources(controller, attempts, delay):
    niches = [niche for niche in trends.NICHES
              if not controller.config.niche or niche['name'] == controller.config.niche]
    research = trends.TrendResearchAgent(controller.engine, niches=niches)
    if not controller.state.get('research_run_id'):
        batch.connect_discovery(controller, attempts, delay)
    return controller.connected(lambda: controller.search(research), 'youtube_search', attempts, delay)


def allocate_source(controller, history, attempts, delay):
    scan = scan_sources(controller, attempts, delay)
    reports_by_id = {report['id']: report for report in controller.state.get('source_reports', [])}
    entries = controller.state['clip_entries']
    planned = {source_id: sum(entry['source']['id'] == source_id for entry in entries)
               for source_id in reports_by_id}
    considered = {source_id for source_id, report in reports_by_id.items()
                  if report['outcome'] != 'selected' or planned[source_id] >= controller.config.clips_per_source}
    excluded = controller.state.get('excluded_source_ids', [])
    choices = [source for source in scan['results']
               if source.get('eligible_preview') and source['id'] not in considered
               and source['id'] not in excluded]
    for source in choices:
        # A resumed scan can outlive the eligibility period for unacquired sources.
        published = datetime.fromisoformat(source['published_at'])
        if not datetime.now(timezone.utc) - timedelta(days=14) <= published <= datetime.now(timezone.utc):
            continue
        controller.update(stage='source_selection', source_id=source['id'], source_selection=source)
        directory = controller.folder / 'source-captions' / source['id']
        directory.mkdir(parents=True, exist_ok=True)
        metadata_path = directory / 'source.json'
        try:
            if metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
                if metadata['id'] != source['id']:
                    raise ValueError('Cached captions belong to a different source')
            else:
                metadata = batch.connected(controller, lambda: sections.inspect_source(source, directory),
                                           'source_captions', attempts, delay)
                atomic_json(metadata_path, metadata)
            duration = metadata.get('duration')
            if (metadata['id'] != source['id'] or isinstance(duration, bool)
                    or not isinstance(duration, (int, float)) or not math.isfinite(duration)
                    or not trends.MIN_SOURCE_SECONDS < duration <= trends.MAX_SOURCE_SECONDS):
                raise media.SourceAccessRequired('Source metadata is outside the long-video eligibility rules')
            previous = [record for record in history if record['source_id'] == source['id']]
            try:
                candidates = sections.select_moments(metadata, 20, controller.config.duration,
                                                    strict=True, excluded=previous)
            except ValueError:
                candidates = []
        except media.SourceAccessRequired:
            candidates = []
        remaining = controller.config.clip_count - len(controller.state['clip_entries'])
        maximum = min(controller.config.clips_per_source - planned.get(source['id'], 0), remaining)
        selected = []
        for moment in candidates:
            if clip_history.repeated_takeaway(moment['source_excerpt'], history):
                continue
            selected.append(moment)
            history.append({'source_id': source['id'], 'clip_plan': moment['clip_plan'],
                            'source_excerpt': moment['source_excerpt'], 'order_id': controller.state['id']})
            if len(selected) == maximum:
                break
        report = {'id': source['id'], 'outcome': 'selected' if selected else 'no_usable_moments_or_captions',
                  'planned_clips': planned.get(source['id'], 0) + len(selected)}
        reports = [item for item in controller.state.get('source_reports', []) if item['id'] != source['id']]
        reports.append(report)
        entries = controller.state['clip_entries']
        for moment in selected:
            entries.append({'number': len(entries) + 1, 'source': source, 'moment': moment,
                            'source_clip_plan': moment['clip_plan'],
                            'metadata_path': metadata_path.relative_to(controller.folder).as_posix()})
        controller.update(source_reports=reports, clip_entries=entries, planned_clip_count=len(entries))
        if selected:
            return True
    return False


def write_index(controller, delivery, partial=False):
    prefix = controller.state['id'][:8]
    path = delivery / f'{prefix}-{"PARTIAL" if partial else "CLIPS"}.txt'
    clips = controller.state['batch_results']
    lines = [f'{len(clips)} of {controller.config.clip_count} clips | order {controller.state["id"]}',
             'Prepared for review. Publishing is disabled.', '']
    for clip in clips:
        lines += [f'{clip["number"]:02d}. {clip["clip"]}', clip['post_caption'],
                  clip['selection_note'], '']
    temporary = path.with_suffix('.txt.tmp')
    temporary.write_text('\n'.join(lines), encoding='utf-8')
    os.replace(temporary, path)
    return path


def skip_source(controller, index, outcome='partial_access_refused'):
    entries = controller.state['clip_entries']
    abandoned = entries[index:]
    reports = controller.state.get('source_reports', [])
    for report in reports:
        if report['id'] == entries[index]['source']['id']:
            report['outcome'] = outcome
    controller.update(clip_entries=entries[:index], source_reports=reports,
                      skipped_entries=[*controller.state.get('skipped_entries', []), *abandoned])


def skip_bad_captions(controller, index):
    entries = controller.state['clip_entries']
    entry = entries[index]
    controller.engine.cancel(entry['job_id'])
    entry['skip_reason'] = 'automatic_caption_quality'
    source_id = entry['source']['id']
    failures = sum(item.get('skip_reason') == 'automatic_caption_quality'
                   and item['source']['id'] == source_id for item in controller.state.get('skipped_entries', []))
    if failures >= 2:
        # Repeated failures suggest an unsuitable source, not just one bad window.
        skip_source(controller, index, outcome='captions_unusable')
        return
    entries.pop(index)
    for number, remaining in enumerate(entries[index:], start=index + 1):
        if remaining.get('job_id'):
            raise ValueError('Cannot renumber an already processed later clip')
        remaining['number'] = number
    controller.update(clip_entries=entries,
                      skipped_entries=[*controller.state.get('skipped_entries', []), entry])


def run_production(controller, attempts, delay):
    atomic_json(controller.orders / 'latest.json', {'id': controller.state['id']})
    controller.engine = ClippingWorkflow(controller.folder / 'workflow.db', controller.storage)
    delivery = (Path(controller.config.delivery_dir) if controller.config.delivery_dir
                else Path(__file__).resolve().parents[1] / 'clips').resolve()
    delivery.mkdir(parents=True, exist_ok=True)
    prefix = controller.state['id'][:8]
    for path in (controller.folder / 'result.json', delivery / f'{prefix}-result.json',
                 delivery / f'{prefix}-CLIPS.txt'):
        path.unlink(missing_ok=True)
    latest = delivery / 'LATEST-CLIPS.txt'
    if latest.is_file() and controller.state['id'] in latest.read_text(encoding='utf-8')[:512]:
        latest.unlink()
    refresh_scan = controller.state['status'] == 'insufficient_sources'
    controller.update(status='running', stage='preflight', action=None, reason=None, result=None,
                      review=None, delivery_dir=str(delivery), requested_clip_count=controller.config.clip_count,
                      batch_results=[], completed_clip_count=0, partial_index=None,
                      clip_entries=controller.state.get('clip_entries', []), full_video_downloaded=False)
    if refresh_scan:
        controller.update(research_run_id=None)
    entries = controller.state['clip_entries']
    all_done = len(entries) == controller.config.clip_count and all(
        entry.get('job_id') and controller.engine.get(entry['job_id'])['status'] == 'completed' for entry in entries)
    if not all_done:
        provider = controller.state.get('discovery_provider') or controller.config.provider
        orchestrator.check_environment(replace(controller.config, provider=provider), controller.storage)
    previous = controller.store.reservations(controller.state['id'])
    history = previous + current_reservations(entries + controller.state.get('skipped_entries', []),
                                              controller.state['id'])
    index = 0
    while len(controller.state['batch_results']) < controller.config.clip_count:
        entries = controller.state['clip_entries']
        if index >= len(entries):
            if not allocate_source(controller, history, attempts, delay):
                partial = write_index(controller, delivery, partial=True)
                controller.update(status='insufficient_sources', stage='source_selection',
                    reason='insufficient_distinct_moments', partial_index=str(partial),
                    action='Verified partial clips are saved. Resume later to search for more eligible sources.')
                return controller.state
            entries = controller.state['clip_entries']
        entry = entries[index]
        moment = entry['moment']
        controller.update(active_clip=entry['number'], job_id=entry.get('job_id'),
                          source_id=entry['source']['id'], source_selection=entry['source'])
        try:
            if not entry.get('job_id'):
                job = batch.create_clip_job(controller, entry, moment, metadata_for(controller, entry), attempts, delay)
            else:
                job = controller.engine.get(entry['job_id'])
        except SetupIssue as exc:
            if exc.code != 'partial_source_access_required':
                raise
            skip_source(controller, index)
            history = previous + current_reservations(
                controller.state['clip_entries'] + controller.state.get('skipped_entries', []), controller.state['id'])
            continue
        if job['status'] == 'running':
            controller.engine._save(job['id'], job['output'], 'queued', job['current_step'],
                                    error='Recovered interrupted production controller')
        if job['status'] != 'completed':
            job = controller.connected(controller.prepare, 'prepare_clip', attempts, delay)
        if job['output'].get('failure_code') == 'source_access_required':
            skip_source(controller, index)
            history = previous + current_reservations(
                controller.state['clip_entries'] + controller.state.get('skipped_entries', []), controller.state['id'])
            continue
        if job['status'] == 'awaiting_transcript' and job['payload'].get('source_reference'):
            skip_bad_captions(controller, index)
            history = previous + current_reservations(
                controller.state['clip_entries'] + controller.state.get('skipped_entries', []), controller.state['id'])
            continue
        if job['status'] != 'completed':
            controller.update(status='transcript_required' if job['status'] == 'awaiting_transcript' else 'failed',
                              reason='section_processing_incomplete', stage=job['current_step'],
                              action='Correct the saved section processing stage, then resume this order.')
            return controller.state
        batch.deliver_clip(controller, job, entry, moment, delivery)
        index += 1
    clips = controller.state['batch_results']
    if len(clips) != controller.config.clip_count:
        raise ValueError('Production run did not reach the requested count')
    index_path = write_index(controller, delivery)
    sources = list({clip['source']['id']: clip['source'] for clip in clips}.values())
    result = {'order_id': controller.state['id'], 'clips': clips, 'sources': sources,
              'requested_clip_count': controller.config.clip_count, 'delivery_dir': str(delivery),
              'index': str(index_path), 'full_video_downloaded': False, 'human_review_required': True,
              'selection_note': 'Transcript/replay ranking assists selection; virality and perfect ASR are not guaranteed.'}
    atomic_json(controller.folder / 'result.json', result)
    atomic_json(delivery / f'{prefix}-result.json', result)
    batch.copy_delivery(index_path, delivery / 'LATEST-CLIPS.txt')
    (delivery / f'{prefix}-PARTIAL.txt').unlink(missing_ok=True)
    controller.update(status='ready_for_review', stage='finished', result=result, reason=None,
                      partial_index=None, action='Open the clip index and review the exports and captions before posting.')
    return controller.state


def execute_production(controller, attempts, delay):
    shared = controller.storage / 'production'
    shared.mkdir(exist_ok=True)
    try:
        with order_lock(shared):
            return run_production(controller, attempts, delay)
    except OrderBusy:
        controller.update(status='already_running', reason='another_production_order_in_use',
                          action='Another production run is active. Resume this order when it finishes.')
        return controller.state
