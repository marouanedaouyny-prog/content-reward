"""Checkpointed highlights from one searched source, using only selected ranges."""

import json
import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from clipping import media, orchestrator, sections, trends
from clipping.orchestrator import ConnectionIssue, SetupIssue, atomic_json
from clipping.workflow import ClippingWorkflow


def cache_for(controller):
    if not hasattr(controller, 'cache'):
        from app.repositories.cache import CacheRepository
        controller.cache = CacheRepository(controller.store)
    return controller.cache


def connected(controller, action, stage, attempts, delay):
    def acquire():
        try:
            result = action()
        except media.SourceUnavailable as exc:
            controller.update(source_failure=exc.diagnostic)
            raise ConnectionIssue('partial_source_connection_unavailable') from exc
        except media.SourceSetupRequired as exc:
            controller.update(source_failure=exc.diagnostic)
            raise SetupIssue('source_' + exc.diagnostic['reason']) from exc
        except media.SourceAccessRequired as exc:
            controller.update(source_failure=exc.diagnostic)
            raise
        if controller.state.get('source_failure'):
            controller.update(source_failure=None)
        return result
    return controller.connected(acquire, stage, attempts, delay)


def connect_discovery(controller, attempts, delay):
    provider = controller.state.get('discovery_provider') or controller.config.provider
    if provider not in ('selenium', 'public'):
        raise ValueError('Invalid saved discovery provider')
    os.environ['CLIPPING_DISCOVERY_PROVIDER'] = 'selenium' if provider == 'selenium' else ''
    effective = replace(controller.config, provider=provider)
    controller.update(discovery_provider=provider)
    try:
        controller.connected(lambda: orchestrator.check_browser(effective), 'source_connectivity', attempts, delay)
    except SetupIssue as exc:
        fallback_codes = {'browser_session_not_created', 'browser_execution_refused',
                          'driver_or_browser_unavailable', 'selenium_unavailable'}
        if provider != 'selenium' or exc.code not in fallback_codes:
            raise
        controller.update(status='running', stage='discovery_fallback', discovery_provider='public',
                          fallback_reason=exc.code, research_run_id=None, rejected_sources=[],
                          source_id=None, source_selection=None)
        os.environ['CLIPPING_DISCOVERY_PROVIDER'] = ''
        effective = replace(controller.config, provider='public')
        controller.connected(lambda: orchestrator.check_browser(effective), 'source_connectivity', attempts, delay)


def choose_source(controller, research, attempts, delay):
    cache = cache_for(controller)
    metadata_path = controller.folder / 'source.json'
    if controller.state.get('moments'):
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if metadata['id'] != controller.state['source_id']:
            raise ValueError('Saved source does not match this batch')
        return metadata
    connect_discovery(controller, attempts, delay)
    scan = controller.connected(lambda: controller.search(research), 'youtube_search', attempts, delay)
    controller.update(stage='source_selection', sources_found=len(scan['results']))
    from growth.source import SourcePreFilter
    from app.core.config import load_settings
    source_filter = SourcePreFilter(load_settings().source_filter)
    while True:
        rejected = controller.state.get('rejected_sources', [])
        excluded = controller.state.get('excluded_source_ids', [])
        choices = [source for source in scan['results'] if source.get('eligible_preview')
                   and source['id'] not in rejected and source['id'] not in excluded]
        choices = source_filter.rank(choices, keywords=controller.config.niche)
        if len(rejected) >= 3 or not choices:
            raise SetupIssue('no_accessible_sources')
        source = choices[0]
        controller.update(source_id=source['id'], source_selection=source)
        try:
            # Each candidate has its own caption files, so failed candidates cannot leak subtitles.
            folder = controller.folder / 'source-captions' / source['id']
            metadata = connected(controller, lambda source=source, folder=folder: sections.inspect_source(
                                 source, folder, cache=cache),
                                 'source_captions', attempts, delay)
            try:
                from analytics.feedback import feedback_for_order
                moments = sections.select_moments(metadata, controller.config.clip_count, controller.config.duration,
                                                  feedback=feedback_for_order(controller))
            except ValueError as exc:
                raise media.SourceAccessRequired('This source has too few usable moments for this order.') from exc
        except media.SourceAccessRequired:
            controller.update(stage='source_selection', rejected_sources=[*rejected, source['id']],
                              rejection_reason='public_captions_or_distinct_moments_unavailable')
            continue
        atomic_json(metadata_path, metadata)
        controller.update(moments=moments, clip_entries=[{'number': number + 1} for number in range(len(moments))],
                          planned_clip_count=len(moments), full_video_downloaded=False)
        return metadata


def create_clip_job(controller, entry, moment, metadata, attempts, delay):
    from clipping.quality.validation import validate_candidate
    from clipping.planning import chapter_conflicts
    assessment = validate_candidate(moment, strict=bool(entry.get('source')))
    if not assessment.passed:
        raise SetupIssue('candidate_quality_failed')
    if entry.get('source') and chapter_conflicts(moment['clip_plan'], metadata.get('chapters'),
                                                source_duration=metadata.get('duration')):
        raise SetupIssue('candidate_chapter_excluded')
    source = entry.get('source') or controller.state['source_selection']
    campaign = controller.store.get_campaign(controller.config.campaign_id) if controller.config.campaign_id else None
    if campaign:
        from campaigns.validation import validate_campaign
        evaluation = validate_campaign(campaign,
            dict(duration_seconds=moment['clip_plan']['duration_seconds'], source_id=source['id'],
                 transcript=moment.get('source_excerpt', '')),
            {'caption': moment['caption'] + ' ' + source.get('title', '') + ' '
                        + ' '.join(campaign.rules.required_hashtags)}, campaign.platform, source=source)
        if not evaluation.eligible:
            raise SetupIssue('campaign_validation_failed')
        entry['campaign_validation'] = evaluation.model_dump()
    number = entry['number']
    folder = controller.folder / 'sections' / f'{number:02d}'
    original_plan = moment['clip_plan']
    if entry.get('source'):
        folder /= (f'{source["id"]}-{original_plan["start_seconds"]:g}-'
                   f'{original_plan["duration_seconds"]:g}')
    try:
        cache = cache_for(controller)
        section = connected(controller, lambda: sections.download_section(source, moment['clip_plan'],
            metadata['duration'], folder, cache=cache), 'partial_download', attempts, delay)
    except media.SourceAccessRequired as exc:
        # Keep the whole batch on its chosen source; never mix sources after selection.
        raise SetupIssue('partial_source_access_required') from exc
    local_plan = {**original_plan, 'start_seconds': section['local_start']}
    creator = source.get('creator') or ''
    styles = controller.config.caption_styles or [controller.config.caption_style]
    caption_style = styles[(number - 1) % len(styles)]
    caption = moment['caption'].strip() + '\n\nFrom: ' + source['title'][:180]
    if creator:
        caption += '\nSource: ' + creator
    if campaign:
        caption += '\n\n' + ' '.join(campaign.rules.required_hashtags)
    data = {'campaign': {'title': 'Highlight: ' + source['title'][:160], 'url': source['url'],
        'platform': 'youtube', 'rules': 'Private local highlight. No publishing or submission.',
        'rights_notes': 'Research source; private local preview.', 'duration_min': 15, 'duration_max': 60},
        'preview_only': True, 'dry_run': False, 'source_path': section['path'].relative_to(controller.storage).as_posix(),
        'language': 'en', 'clip_plan': local_plan, 'caption': caption,
        'caption_style': caption_style, 'framing_mode': controller.config.framing_mode,
        'growth': moment.get('growth'), 'source_selection': source}
    if campaign:
        data['campaign'].update(title=campaign.title, platform=campaign.platform,
                                duration_min=campaign.rules.min_duration, duration_max=campaign.rules.max_duration,
                                campaign_id=campaign.id)
    key = f'batch:{controller.state["id"]}:{number}'
    if entry.get('source'):
        key += f':{source["id"]}:{original_plan["start_seconds"]}'
    begin = original_plan['start_seconds']
    end = begin + original_plan['duration_seconds']
    data['source_reference'] = [
        {'start': max(cue['start'], begin) - section['source_offset'],
         'end': min(cue['end'], end) - section['source_offset'], 'text': cue['text']}
        for cue in metadata['segments'] if cue['start'] < end and cue['end'] > begin]
    if not data['source_reference']:
        raise ValueError('Selected moment has no source speech reference')
    data['source_reference_origin'] = metadata.get('transcript_origin', 'public_source_captions')
    job = controller.engine.create(data, key)
    entry.update(pre_render_quality=assessment.model_dump(), job_id=job['id'], section_sha256=section['sha256'], source_offset=section['source_offset'],
                 source_clip_plan=original_plan, local_clip_plan=local_plan, post_caption=caption,
                 caption_style=caption_style)
    controller.update(clip_entries=controller.state['clip_entries'], job_id=job['id'], active_clip=number)
    return job


def copy_delivery(source, target):
    if target.is_symlink():
        raise ValueError('Delivery targets must not be symbolic links')
    if target.is_file() and media.file_hash(target) == media.file_hash(source):
        return
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name + '.', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)
        if media.file_hash(temporary) != media.file_hash(source):
            raise ValueError('Delivery copy did not match the verified export')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def write_caption(target, content):
    if target.is_symlink():
        raise ValueError('Caption targets must not be symbolic links')
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                     prefix=target.name + '.', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(content, encoding='utf-8')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def deliver_clip(controller, job, entry, moment, delivery):
    if entry.get('source'):
        from clipping.quality.validation import validate_candidate
        from clipping.planning import chapter_conflicts
        from clipping.production import metadata_for
        if not validate_candidate(moment, strict=True).passed:
            raise SetupIssue('candidate_quality_failed')
        metadata = metadata_for(controller, entry)
        if chapter_conflicts(entry['source_clip_plan'], metadata.get('chapters'),
                             source_duration=metadata.get('duration')):
            raise SetupIssue('candidate_chapter_excluded')
    controller.update(stage='export_review', status='running', active_clip=entry['number'])
    # Manual local windows still need a selected plan for the shared mechanical verifier.
    output = dict(job['output'], selected_clip_plan=entry['local_clip_plan'])
    review = orchestrator.verify_export(controller.engine, {**job, 'output': output},
                           controller.folder / f'review-{entry["number"]:02d}')
    source = entry.get('source') or controller.state['source_selection']
    from clipping.library import IDS, niche_folder, niche_routing
    routing = niche_routing(source, controller.config.niche, excerpt=moment.get('source_excerpt') or '',
                            review=entry.get('niche_review'))
    try:
        saved_clip = controller.store.get_clip(job['id'])
        saved_settings = saved_clip.get('settings') or {}
    except KeyError:
        saved_settings = {}
    if entry.get('niche_review') is None and saved_settings.get('delivery_niche') in IDS:
        # Resuming a completed export preserves its saved classification. A new
        # per-clip editorial review is the explicit way to revise that decision.
        saved_routing = saved_settings.get('niche_routing')
        routing = (saved_routing if isinstance(saved_routing, dict)
                   and saved_routing.get('niche') == saved_settings['delivery_niche'] else dict(
                       niche=saved_settings['delivery_niche'], basis='saved_delivery_niche',
                       needs_review=saved_settings['delivery_niche'] == 'unclassified'))
    delivery_niche = routing['niche']
    delivery_root = delivery
    if controller.config.organize_by_niche:
        delivery = niche_folder(delivery, delivery_niche)
        delivery.mkdir(parents=True, exist_ok=True)
    prefix = f'{controller.state["id"][:8]}-{source["id"]}-{entry["number"]:02d}'
    caption_style = job['payload'].get('caption_style', controller.config.caption_style)
    if controller.config.caption_styles:
        prefix += '-' + caption_style
    clip = delivery / f'{prefix}.mp4'
    revision = saved_settings.get('caption_revision')
    if revision:
        from clipping.recovery import _safe_path
        if (revision.get('clip_id') != job['id'] or revision.get('request_hash') !=
                job['payload'].get('caption_revision', {}).get('request_hash')):
            raise ValueError('caption_revision_saved_provenance_disagreement')
        # A correction has a separate immutable name and may have an explicitly
        # reviewed niche even when this historical order uses flat delivery.
        clip = _safe_path(saved_clip['path'], delivery_root)
        delivery, prefix = clip.parent, clip.stem
        delivery.mkdir(parents=True, exist_ok=True)
    subtitles = delivery / f'{prefix}.srt'
    copy_delivery(controller.engine.artifact(job['id'], 'clip'), clip)
    copy_delivery(controller.engine.artifact(job['id'], 'subtitles'), subtitles)
    styled = output.get('styled_subtitle_path')
    if styled:
        copy_delivery(controller.engine.safe_path(styled), delivery / f'{prefix}.ass')
    caption_path = delivery / f'{prefix}-caption.txt'
    write_caption(caption_path, entry['post_caption'])
    delivery_hashes = {'video': media.file_hash(clip), 'subtitles': media.file_hash(subtitles),
                       'post_caption': media.file_hash(caption_path)}
    result = {'number': entry['number'], 'job_id': job['id'], 'clip': str(clip),
              'subtitles': str(subtitles), 'post_caption': entry['post_caption'],
              'source': source, 'source_clip_plan': entry['source_clip_plan'],
              'local_clip_plan': entry['local_clip_plan'], 'source_offset': entry['source_offset'],
              'selection_note': moment['note'], 'selection_quality': moment.get('quality'),
              'diversity_note': moment.get('diversity_note'),
              'caption_style': caption_style, 'framing_mode': controller.config.framing_mode,
              'render_template': output.get('render_template'), 'review': review}
    result['delivery_niche'] = delivery_niche
    result['niche_routing'] = routing
    if revision:
        result['caption_revision'] = revision
    from app.repositories.store import moment_identifier
    controller.store.save_clip(dict(id=job['id'], order_id=controller.state['id'], source_id=source['id'],
        moment_id=moment_identifier(controller.state['id'], source['id'], entry['source_clip_plan']),
        path=str(clip), subtitles=str(subtitles), sha256=media.file_hash(clip), caption=entry['post_caption'],
        caption_style=caption_style, framing=controller.config.framing_mode,
        settings=dict(saved_settings, source_clip_plan=entry['source_clip_plan'], review=review,
                      selection_quality=moment.get('quality'), selection_score=moment.get('selection'),
                      growth=moment.get('growth'),
                      transcript_features=moment.get('transcript_features'), transcript=moment.get('source_excerpt'),
                      source=source, feedback=moment.get('feedback'), niche=controller.config.niche,
                      delivery_niche=delivery_niche, niche_routing=routing, delivery_hashes=delivery_hashes)))
    controller.update(batch_results=[*controller.state.get('batch_results', []), result],
                      completed_clip_count=len(controller.state.get('batch_results', [])) + 1)


def execute_batch(controller, attempts, delay):
    atomic_json(controller.orders / 'latest.json', {'id': controller.state['id']})
    controller.engine = controller.bind_render_metrics(
        ClippingWorkflow(controller.folder / 'workflow.db', controller.storage))
    delivery = (Path(controller.config.delivery_dir) if controller.config.delivery_dir else
                Path(__file__).resolve().parents[1] / 'clips').resolve()
    delivery.mkdir(parents=True, exist_ok=True)
    entries = controller.state.get('clip_entries', [])
    all_done = entries and all(entry.get('job_id') and controller.engine.get(entry['job_id'])['status'] == 'completed'
                               for entry in entries)
    controller.update(status='running', stage='preflight', action=None, delivery_dir=str(delivery))
    if not all_done:
        provider = controller.state.get('discovery_provider') or controller.config.provider
        orchestrator.check_environment(replace(controller.config, provider=provider), controller.storage)
    # A failed recheck must not leave a stale ready-result manifest for consumers.
    (controller.folder / 'result.json').unlink(missing_ok=True)
    (delivery / f'{controller.state["id"][:8]}-result.json').unlink(missing_ok=True)
    controller.update(status='running', stage='preflight', action=None, result=None, review=None,
                      delivery_dir=str(delivery), batch_results=[], completed_clip_count=0)
    niches = [item for item in trends.NICHES if not controller.config.niche or item['name'] == controller.config.niche]
    metadata = choose_source(controller, trends.TrendResearchAgent(controller.engine, niches=niches,
        cache_database=controller.store.path), attempts, delay)
    for entry, moment in zip(controller.state['clip_entries'], controller.state['moments']):
        controller.update(active_clip=entry['number'], job_id=entry.get('job_id'))
        if not entry.get('job_id'):
            job = create_clip_job(controller, entry, moment, metadata, attempts, delay)
        else:
            job = controller.engine.get(entry['job_id'])
        if job['status'] == 'running':
            controller.engine._save(job['id'], job['output'], 'queued', job['current_step'],
                                    error='Recovered interrupted batch controller')
        if job['status'] != 'completed':
            job = controller.connected(controller.prepare, 'prepare_clip', attempts, delay)
        if job['status'] != 'completed':
            controller.update(status='transcript_required' if job['status'] == 'awaiting_transcript' else 'failed',
                              reason='section_speech_transcript_required' if job['status'] == 'awaiting_transcript'
                              else 'section_preparation_failed', stage=job['current_step'],
                              action='Correct the section processing stage, then resume this saved batch.')
            return controller.state
        deliver_clip(controller, job, entry, moment, delivery)
    results = controller.state['batch_results']
    if not min(3, controller.config.clip_count) <= len(results) <= controller.config.clip_count:
        raise ValueError('Order did not produce the requested number of verified clips')
    result = {'order_id': controller.state['id'], 'clips': results, 'delivery_dir': str(delivery),
              'full_video_downloaded': False, 'source': controller.state['source_selection'],
              'human_review_required': True}
    atomic_json(controller.folder / 'result.json', result)
    atomic_json(delivery / f'{controller.state["id"][:8]}-result.json', result)
    controller.update(status='ready_for_review', stage='finished', result=result, reason=None,
                      action='Review the saved highlights, spoken captions and source context.')
    return controller.state
