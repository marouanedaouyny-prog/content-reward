"""Caption-first planning and bounded time-range acquisition; never full media."""

import html
import json
import math
import re
import shutil
import subprocess

from clipping import media
from clipping.planning import sentence_ending, suggest_cuts, usable_heatmap
from app.core.config import load_settings
from clipping.selection.dedup import compare_moments


def remote_command(args, timeout):
    try:
        return media.command(args, timeout=timeout, kill_tree=True)
    except (ValueError, subprocess.TimeoutExpired) as exc:
        raise media.classify_source_failure(exc) from exc


def parse_captions(data, duration):
    if not isinstance(data, dict) or not isinstance(data.get('events'), list):
        raise ValueError('No usable public captions')  # noqa: TRY004 - malformed caption documents share one validation error.
    cues = []
    for event in data['events'][:50000]:
        if not isinstance(event, dict):
            continue
        try:
            start = float(event['tStartMs']) / 1000
            end = min(duration, start + float(event['dDurationMs']) / 1000)
            text = ' '.join(html.unescape(''.join(piece.get('utf8', '') for piece in
                event.get('segs', []) if isinstance(piece, dict))).split())
        except (KeyError, TypeError, ValueError):
            continue
        if not text or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration:
            continue
        if re.fullmatch(r'\[(?:music|applause|laughter)\]', text, re.IGNORECASE):
            continue
        cues.append({'start': start, 'end': end, 'text': text})
    cues.sort(key=lambda cue: (cue['start'], cue['end']))
    clean = []
    for cue in cues:
        if clean and cue['start'] < clean[-1]['end']:
            if cue['text'] == clean[-1]['text']:
                clean[-1]['end'] = max(clean[-1]['end'], cue['end'])
                continue
            clean[-1]['end'] = cue['start']
            if clean[-1]['end'] <= clean[-1]['start']:
                clean.pop()
        clean.append(cue)
    # Join unfinished public-caption cues, without inventing word timestamps.
    merged = []
    for cue in clean:
        if (merged and not sentence_ending(merged[-1]['text']) and
                cue['start'] - merged[-1]['end'] <= 1.5 and cue['end'] - merged[-1]['start'] <= 12):
            merged[-1].update(end=cue['end'], text=merged[-1]['text'] + ' ' + cue['text'])
        else:
            merged.append(dict(cue))
    if not merged or len(merged) > 5000:
        raise ValueError('No usable public captions within planning limits')
    return merged


def inspect_source(source, folder, *, cache=None):
    folder.mkdir(parents=True, exist_ok=True)
    identity = {'youtube_video_id': source['id'], 'caption_language': 'en', 'parser_version': 1}
    if cache is not None:
        cached = cache.get_json('source_transcript_replay', identity, max_bytes=8_000_000)
        if (isinstance(cached, dict) and cached.get('id') == source['id']
                and isinstance(cached.get('segments'), list) and 0 < len(cached['segments']) <= 5000
                and isinstance(cached.get('duration'), (int, float)) and cached['duration'] > 0):
            return {**cached, 'title': str(source.get('title') or cached.get('title') or '')[:500],
                'view_count': source.get('views', cached.get('view_count')),
                'like_count': source.get('likes', cached.get('like_count')),
                'comment_count': source.get('comments', cached.get('comment_count')),
                'published_at': source.get('published_at', cached.get('published_at'))}
    # Print only safe metadata, never stream URLs, cookies, headers or the full info dict.
    fields = '%(.{id,title,duration,view_count,like_count,comment_count,upload_date,channel,uploader,heatmap,chapters})j'
    response = remote_command([*media.ytdlp_command(), '--ignore-config', '--no-playlist',
        '--skip-download', '--no-simulate', '--write-subs', '--write-auto-subs',
        '--sub-langs', 'en-orig,en,en-US,en-GB', '--sub-format', 'json3',
        # A rate limit on one redundant track must not discard the tracks that
        # already downloaded; any parseable track is sufficient.
        '--ignore-errors',
        '--socket-timeout', '15', '--retries', '2', '--extractor-retries', '1',
        '--print', fields, '-o', str(folder / 'captions.%(ext)s'), source['url']], 120)
    try:
        raw = json.loads(response)
        duration = float(raw['duration'])
        if raw['id'] != source['id'] or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Unexpected source metadata')
        segments = None
        for language in ('en', 'en-orig', 'en-US', 'en-GB'):
            path = folder / f'captions.{language}.json3'
            if not path.is_file() or path.stat().st_size > 8_000_000:
                continue
            try:
                segments = parse_captions(json.loads(path.read_text(encoding='utf-8')), duration)
                break
            except (ValueError, TypeError):
                continue
        if not segments:
            raise ValueError('No public English transcript')
        result = {'id': raw['id'], 'title': str(raw.get('title') or '')[:500],
                'duration': duration, 'segments': segments,
                'heatmap': usable_heatmap(raw.get('heatmap'), duration),
                'view_count': raw.get('view_count'), 'like_count': raw.get('like_count'),
                'comment_count': raw.get('comment_count'), 'published_at': source.get('published_at'),
                'chapters': raw.get('chapters') if isinstance(raw.get('chapters'), list) else [],
                'transcript_origin': 'youtube_public_captions'}
        if cache is not None:
            cache.put_json('source_transcript_replay', identity, result, ttl_seconds=6 * 3600,
                           max_bytes=8_000_000)
        return result
    except (ValueError, KeyError, TypeError) as exc:
        raise media.SourceAccessRequired('This source has no usable public English captions; no full download was attempted.') from exc


def _content_words(text, excluded):
    return [word for word in re.findall(r"[a-zA-Z][a-zA-Z']{2,}", text.lower()) if word not in excluded]


def _repeated_signature(signature, previous, threshold):
    shared = len(signature & previous)
    union, shorter = len(signature | previous), min(len(signature), len(previous))
    return bool(union and shared / union >= threshold or shorter >= 5 and shared / shorter >= threshold)


def select_moments(source, count, target, *, strict=False, excluded=(), settings=None, feedback=None):
    settings = settings or load_settings()
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 20:
        raise ValueError('Choose a clip count from one through 20')
    # Source-title terms are useful for all niches; exclude common context words.
    stop = {'the', 'and', 'for', 'with', 'this', 'that', 'you', 'your', 'how', 'why',
            'what', 'can', 'are', 'from', 'full', 'podcast', 'interview', 'episode'}
    keywords = ', '.join(_content_words(source.get('title', ''), stop))[:200]
    excluded = list(excluded)
    reserved = [item['clip_plan'] for item in excluded]
    choices = []
    common = stop | {'one', 'two', 'three', 'four', 'five', 'have', 'has', 'had', 'was', 'were',
                     'been', 'will', 'would', 'could', 'should', 'not', 'but', 'they', 'them', 'their'}
    signatures = [set(_content_words(item.get('source_excerpt', ''), common)) for item in excluded]
    while len(choices) < count:
        try:
            pool = suggest_cuts(source['segments'], source['duration'], target, 15, 60,
                keywords, source.get('heatmap'), limit=20, min_gap=3,
                excluded_windows=reserved, require_standalone=strict, settings=settings, source=source,
                rank_by_growth=True, feedback=feedback)
        except ValueError as exc:
            if 'No complete transcript window' not in str(exc):
                raise
            break
        # Refill after text exclusions, rather than letting twenty repeated peaks
        # hide a later useful moment. Every considered interval is retired.
        reserved.extend(choice['clip_plan'] for choice in pool)
        for choice in pool:
            if choice['quality']['promotional']:
                continue
            if strict and choice['selection']['score'] < settings.selection.minimum_score:
                continue
            if any(compare_moments(choice, previous, settings=settings)['duplicate'] for previous in [*excluded, *choices]):
                continue
            signature = set(_content_words(choice['source_excerpt'], common))
            if any(_repeated_signature(signature, previous, settings.dedup.transcript_similarity_threshold)
                   for previous in signatures):
                continue
            choice['diversity_note'] = ('Separate source window with no near-duplicate normalized transcript '
                'in this batch or supplied history. Distinct takeaways still need editorial review.')
            choices.append(choice)
            signatures.append(signature)
            if len(choices) == count:
                break
    if not choices:
        raise ValueError('No usable transcript moment fits the duration limits')
    if not strict and len(choices) < min(count, 3):
        raise ValueError('Fewer than three distinct transcript moments fit the duration limits')
    for choice in choices:
        if choice['score_type'] == 'editorial_heuristic':
            choice['note'] = 'YouTube replay data unavailable. ' + choice['note']
    return choices


def _validate_section(path, expected_duration, minimum_duration):
    info = media.probe(path)
    duration = float(info['format']['duration'])
    kinds = {stream.get('codec_type') for stream in info.get('streams', [])}
    if (not math.isfinite(duration) or abs(duration - expected_duration) > 1.2 or
            duration + .15 < minimum_duration or not {'video', 'audio'} <= kinds
            or path.stat().st_size > 120 * 1024 * 1024):
        raise ValueError('Downloaded section is not the requested bounded audio/video window')
    return duration


def download_section(source, plan, source_duration, folder, *, cache=None):
    start, length = plan['start_seconds'], plan['duration_seconds']
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in (start, length, source_duration)) or start < 0 or not 15 <= length <= 60
            or start + length > source_duration + .15):
        raise ValueError('Invalid partial source window')
    begin, end = max(0, start - 3), min(source_duration, start + length + 3)
    folder.mkdir(parents=True, exist_ok=True)
    files = [folder / f'section{suffix}' for suffix in ('.mp4', '.mkv', '.webm')]
    path = next((candidate for candidate in files if candidate.is_file()), None)
    cache_identity = ({'youtube_video_id': source['id'], 'source_offset': begin,
        'requested_end': end, 'format': 'bounded-audio-video-v1'} if cache is not None else None)
    cache_result, reused_bytes = None, None
    if path is not None:
        try:
            duration = _validate_section(path, end - begin, start - begin + length)
        except (ValueError, KeyError, TypeError):
            # An interrupted download is not a checkpoint; reacquire only this range.
            path.unlink()
            path = None
    if path is None:
        if cache is not None:
            cached_path = cache.get_file('downloaded_section', cache_identity)
            if cached_path is not None and cached_path.suffix in ('.mp4', '.mkv', '.webm'):
                path = folder / ('section' + cached_path.suffix)
                shutil.copy2(cached_path, path)
                try:
                    duration = _validate_section(path, end - begin, start - begin + length)
                    cache_result = 'exact_hit'
                    reused_bytes = path.stat().st_size
                except (ValueError, KeyError, TypeError):
                    path.unlink(missing_ok=True)
                    path = None
            if path is None and hasattr(cache, 'find_file'):
                containing = cache.find_file('downloaded_section', lambda identity:
                    identity.get('youtube_video_id') == source['id']
                    and identity.get('format') == 'bounded-audio-video-v1'
                    and isinstance(identity.get('source_offset'), (int, float))
                    and isinstance(identity.get('requested_end'), (int, float))
                    and identity['source_offset'] <= begin
                    and identity['requested_end'] >= end)
                if containing is not None:
                    cached_path, containing_identity = containing
                    trim_offset = begin - containing_identity['source_offset']
                    path = folder / 'section.mp4'
                    try:
                        media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                            '-ss', f'{trim_offset:g}', '-i', str(cached_path), '-t', f'{end - begin:g}',
                            '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'veryfast',
                            '-crf', '18', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                            str(path)], timeout=180)
                        duration = _validate_section(path, end - begin, start - begin + length)
                        cache_result = 'containing_hit'
                        reused_bytes = cached_path.stat().st_size
                    except (ValueError, KeyError, TypeError, OSError, RuntimeError):
                        path.unlink(missing_ok=True)
                        path = None
                        cache_result = 'trim_failed'
        if cache is not None and hasattr(cache, 'record_access'):
            cache.record_access('downloaded_section', cache_result or 'miss',
                reused_bytes=reused_bytes, requested_seconds=length)
    if path is None:
        remote_command([*media.ytdlp_command(), '--ignore-config', '--no-playlist',
            '--no-write-subs', '--no-write-auto-subs', '--socket-timeout', '20',
            '--retries', '2', '--extractor-retries', '1', '--fragment-retries', '2',
            '--download-sections', f'*{begin:g}-{end:g}', '--force-keyframes-at-cuts',
            '--downloader', 'ffmpeg', '--downloader-args', 'ffmpeg_i:-rw_timeout 20000000',
            '-f', 'bv[height<=1080][protocol=https]+ba[protocol=https]/b[height<=1080][protocol=https]',
            '--merge-output-format', 'mp4', '-o', str(folder / 'section.%(ext)s'), source['url']], 300)
        path = next((candidate for candidate in files if candidate.is_file()), None)
        if path is None:
            raise ValueError('Partial download produced no section')
        duration = _validate_section(path, end - begin, start - begin + length)
    if cache is not None:
        cache.put_file('downloaded_section', cache_identity, path, ttl_seconds=7 * 86400)
    return {'path': path, 'source_offset': begin, 'local_start': start - begin,
            'requested_end': end, 'duration': duration, 'sha256': media.file_hash(path)}
