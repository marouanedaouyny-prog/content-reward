"""Real media processing; practice mode uses a harmless generated video."""

import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import textwrap
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from clipping.template import DEFAULT_CAPTION_STYLE, DEFAULT_FRAMING_MODE, TEMPLATE_ID


class TranscriptRequired(Exception):
    pass


class SourceUnavailable(Exception):
    """A temporary network failure, eligible for a saved automatic retry."""


class SourceAccessRequired(Exception):
    """A source-specific refusal; another researched source may be usable."""


class ProcessingInterrupted(Exception):
    """An operator or application shutdown interrupted a media operation."""


_stop_signal = ContextVar('clipping_media_stop', default=None)


@contextmanager
def processing_control(should_stop):
    token = _stop_signal.set(should_stop)
    try:
        yield
    finally:
        _stop_signal.reset(token)


def terminate_process(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=10)


def file_hash(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def command(args, cwd=None, timeout=300, kill_tree=False, should_stop=None):
    should_stop = should_stop or _stop_signal.get()
    if should_stop and should_stop():
        raise ProcessingInterrupted('Processing paused or cancelled')
    try:
        if not kill_tree and not should_stop:
            result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=timeout)
        else:
            if os.name == 'nt':
                from clipping.windows_process import launch
                managed_process = launch(args, cwd)
            else:
                managed_process = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                   text=True, encoding='utf-8', errors='replace', start_new_session=True)
            with managed_process as process:
                try:
                    deadline = time.monotonic() + timeout
                    while True:
                        if should_stop and should_stop():
                            raise ProcessingInterrupted('Processing paused or cancelled')
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(args, timeout)
                        try:
                            stdout, stderr = process.communicate(timeout=min(.5, remaining))
                            break
                        except subprocess.TimeoutExpired:
                            continue
                except (subprocess.TimeoutExpired, ProcessingInterrupted):
                    if os.name != 'nt':
                        terminate_process(process)
                    raise
                result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    except FileNotFoundError as exc:
        raise ValueError(f'Install {args[0]} and make it available on PATH') from exc
    if result.returncode:
        raise ValueError(f'{args[0]} failed: {result.stderr[-2000:]}')
    return result.stdout


def probe(path):
    return json.loads(command(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                               '-of', 'json', str(path)], timeout=30))


def ytdlp_command():
    # Prefer the installed environment over a bundled Windows executable that
    # may be unable to unpack its native files into restricted temporary paths.
    args = [sys.executable, '-m', 'yt_dlp'] if importlib.util.find_spec('yt_dlp') else ['yt-dlp']
    runtime = next((name for name in ('deno', 'node') if shutil.which(name)), None)
    return args + ['--js-runtimes', runtime] if runtime else args


def ingest(data, output, folder, storage):
    source = folder / 'source.mp4'
    downloaded = False
    reused_window = False
    begin = max(0, data['clip_plan']['start_seconds'] - 3)
    end = data['clip_plan']['start_seconds'] + data['clip_plan']['duration_seconds'] + 3
    window_file = folder / 'source-window.json'
    if data['dry_run']:
        duration = data['clip_plan']['start_seconds'] + data['clip_plan']['duration_seconds'] + 1
        if data.get('auto_clip'):
            duration = data['clip_plan']['duration_seconds']
        if duration > 300:
            raise ValueError('Practice mode supports source windows up to 300 seconds')
        command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                 '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=25',
                 '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
                 '-t', str(duration), '-c:v', 'libx264', '-threads', '2',
                 '-preset', 'ultrafast', '-crf', '32', '-c:a', 'aac', str(source)])
    elif data.get('source_path'):
        original = (storage / data['source_path']).resolve()
        if not original.is_relative_to(storage) or not original.is_file():
            raise ValueError('Upload the source video into workflow storage first')
        if original != source:
            shutil.copyfile(original, source)
    else:
        # Exact final filenames exclude video-only format files left by an interrupted merge.
        files = [folder / f'source{suffix}' for suffix in ('.mp4', '.mkv', '.webm', '.mov')
                 if (folder / f'source{suffix}').is_file()]
        reusable = False
        for candidate in files:
            try:
                details = probe(candidate)
                reusable = float(details['format']['duration']) > 0 and any(
                    stream.get('codec_type') == 'video' for stream in details.get('streams', []))
                if window_file.is_file():
                    window = json.loads(window_file.read_text(encoding='utf-8'))
                    reused_window = (window['begin'] == begin and window['end'] == end
                                     and window['sha256'] == file_hash(candidate))
                    reusable = reusable and reused_window
            except (ValueError, KeyError, OSError):
                reusable = False
            if reusable:
                source = candidate
                break
            candidate.unlink()  # Invalid, uncheckpointed final artifact; retain resumable .part files.
        if not reusable:
            options = ['--socket-timeout', '20', '--retries', '3', '--extractor-retries', '2',
                       '--fragment-retries', '5', '--retry-sleep', 'http:exp=1:8',
                       '--retry-sleep', 'fragment:exp=1:8', '--concurrent-fragments', '4',
                       '--continue', '--part', '--abort-on-unavailable-fragments']
            try:
                command([*ytdlp_command(), '--ignore-config', '--no-playlist', '--max-filesize', '500M',
                         '--download-sections', f'*{begin:g}-{end:g}', '--force-keyframes-at-cuts',
                         '--downloader', 'ffmpeg',
                         *options, '-f', 'bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]',
                         '--print-to-file', 'after_move:%(heatmap)j', str(folder / 'source-heatmap.json'),
                         '--merge-output-format', 'mp4', '-o', str(folder / 'source.%(ext)s'),
                         data['source_url']], timeout=1800, kill_tree=True)
                downloaded = True
            except (ValueError, subprocess.TimeoutExpired) as exc:
                transient = isinstance(exc, subprocess.TimeoutExpired) or any(term in str(exc).lower() for term in (
                    'unable to connect to proxy', 'connection refused', '10061', 'timed out',
                    'temporary failure', 'connection reset', 'name resolution', 'getaddrinfo failed',
                    'http error 500', 'http error 502', 'http error 503', 'http error 504', 'http error 429'))
                if transient:
                    raise SourceUnavailable('Source connection temporarily unavailable. Saved partial downloads will resume on retry.') from exc
                if any(term in str(exc).lower() for term in ('http error 403', 'private video',
                        'video unavailable', 'sign in to confirm', 'not available in your country',
                        'members-only', 'copyright')):
                    raise SourceAccessRequired('Source access unavailable. Choose another eligible public source.') from exc
                raise ValueError('Source download failed. Check downloader setup or choose another public source.') from exc
            files = [folder / f'source{suffix}' for suffix in ('.mp4', '.mkv', '.webm', '.mov')
                     if (folder / f'source{suffix}').is_file()]
            source = files[0] if files else None
        if not files:
            raise ValueError('Download produced no usable video file')
        if source.stat().st_size > 500 * 1024 * 1024:
            raise ValueError('Downloaded source exceeds the 500 MB limit; use a shorter authorized source')
    info = probe(source)
    duration = float(info['format']['duration'])
    plan = data['clip_plan']
    local_start = plan['start_seconds'] - begin if downloaded or reused_window else plan['start_seconds']
    if downloaded and duration > end - begin + 1.2:
        raise SourceAccessRequired('Provider did not return the requested bounded source window.')
    if not data.get('auto_clip') and local_start + plan['duration_seconds'] > duration + 0.15:
        raise ValueError(f'Clip window exceeds source duration ({duration:.2f} seconds)')
    result = {'source_path': source.relative_to(storage).as_posix(), 'source_sha256': file_hash(source),
              'source_duration': duration, 'synthetic_source': data['dry_run']}
    if downloaded or reused_window:
        result['source_offset'] = begin
        result['source_clip_plan'] = dict(plan)
        if not data.get('auto_clip'):
            result['selected_clip_plan'] = {**plan, 'start_seconds': local_start}
        window_file.write_text(json.dumps(dict(begin=begin, end=end, sha256=result['source_sha256'])), encoding='utf-8')
    heatmap_file = folder / 'source-heatmap.json'
    if not data['dry_run'] and not data.get('source_path') and heatmap_file.is_file():
        from clipping.planning import usable_heatmap
        try:
            if heatmap_file.stat().st_size <= 256_000:
                # --print-to-file appends; a resumed download may have several lines.
                replay = usable_heatmap(json.loads(heatmap_file.read_text(encoding='utf-8').splitlines()[-1]), duration)
                if replay:
                    result['source_heatmap'] = replay
        except (ValueError, IndexError):
            pass  # Missing replay data must not fabricate popularity or prevent real captions.
    return result


def parse_srt(text):
    segments = []
    timestamp = re.compile(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})')
    for block in re.split(r'\n\s*\n', text.replace('\r', '').strip()):
        lines = block.splitlines()
        timing_index = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if timing_index is None:
            continue
        matches = list(timestamp.finditer(lines[timing_index]))
        if len(matches) != 2:
            raise ValueError('Subtitles need valid SRT timestamps')
        times = [int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000 for m in matches]
        segments.append({'start': times[0], 'end': times[1],
                         'text': ' '.join(lines[timing_index + 1:]).strip()})
    if not segments:
        raise ValueError('No timed subtitles found; paste a valid SRT transcript')
    return segments


def validate_segments(segments, duration):
    if not isinstance(segments, list) or not segments:
        raise ValueError('Transcript must contain timed segments')
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError('Each transcript segment must be an object')
        start, end, text = segment.get('start'), segment.get('end'), segment.get('text')
        if any(isinstance(t, bool) or not isinstance(t, (float, int)) or not math.isfinite(t)
               for t in (start, end)):
            raise ValueError('Transcript timestamps must be finite numbers')
        if not 0 <= start < end <= duration + 0.25 or not isinstance(text, str) or not text.strip():
            raise ValueError('Transcript segments must contain text within the source duration')
        if 'words' in segment:
            words = segment['words']
            if not isinstance(words, list) or not words:
                raise ValueError('Word timestamps must contain timed words')
            previous_end = 0
            for word in words:
                if not isinstance(word, dict):
                    raise ValueError('Word timestamp must be an object')
                word_start, word_end, value = word.get('start'), word.get('end'), word.get('word')
                if any(isinstance(t, bool) or not isinstance(t, (float, int)) or not math.isfinite(t)
                       for t in (word_start, word_end)):
                    raise ValueError('Word timestamps must be finite numbers')
                if not 0 <= word_start <= word_end <= duration + .25 or word_start < previous_end:
                    raise ValueError('Word timestamps must be ordered within the source duration')
                if not isinstance(value, str) or not value.strip():
                    raise ValueError('Word timestamps must contain text')
                previous_end = word_end
            if ' '.join(''.join(word['word'] for word in words).split()) != ' '.join(text.split()):
                raise ValueError('Word text must match its transcript segment')
    return sorted(segments, key=lambda s: (s['start'], s['end']))


def model_files_ready(folder):
    return all((folder / name).is_file() and (folder / name).stat().st_size > 0
               for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'))


def whisper_model_location(storage, language=None):
    configured = os.environ.get('WHISPER_MODEL')
    if configured:
        local = Path(storage) / 'models' / configured
        return str(local) if model_files_ready(local) else configured
    names = ('small', 'tiny.en') if language == 'en' else ('small',)
    for name in names:
        local = Path(storage) / 'models' / name
        if model_files_ready(local):
            return str(local)
    return 'small'


def _infer_transcript(args, duration):
    result = json.loads(command(args, timeout=1800, kill_tree=True))
    if not isinstance(result, dict) or not re.fullmatch(r'[a-z]{2,3}', str(result.get('language', ''))):
        raise ValueError('Invalid transcription response')
    segments = result.get('segments')
    if segments == []:
        raise TranscriptRequired('No speech was detected by automatic transcription. '
                                 'Provide timed SRT subtitles from the source audio to continue.')
    return validate_segments(segments, duration), result['language']


def transcribe(data, output, folder, storage):
    assessment = None
    if data.get('transcript_srt') or data.get('transcript'):
        segments = data.get('transcript') or parse_srt(data['transcript_srt'])
        origin = 'operator_supplied_practice' if data['dry_run'] else 'operator_supplied'
    elif data['dry_run']:
        segments = [{'start': 0, 'end': output['source_duration'],
                     'text': 'Practice clip. No publication or reward submission.'}]
        origin = 'synthetic_practice'
    else:
        try:
            args = [sys.executable, '-I', str(Path(__file__).with_name('_transcribe.py')),
                    str(storage / output['source_path']),
                    whisper_model_location(storage, data.get('language')), str(storage / 'models')]
            if data.get('language'):
                args.extend(['--language', data['language']])
            if data.get('transcription_hint'):
                args.extend(['--initial-prompt', data['transcription_hint']])
            segments, language = _infer_transcript(args, output['source_duration'])
            if data.get('source_reference'):
                from clipping.caption_review import assess_captions
                plan = output.get('selected_clip_plan') or data.get('clip_plan') or {
                    'start_seconds': 0, 'duration_seconds': output['source_duration']}
                def assess():
                    return assess_captions(segments, plan['start_seconds'], plan['duration_seconds'],
                                           data['source_reference'])
                assessment = assess()
                if not assessment['passed'] and '--initial-prompt' in args:
                    prompt_index = args.index('--initial-prompt')
                    segments, language = _infer_transcript(args[:prompt_index], output['source_duration'])
                    assessment = assess()
                if not assessment['passed']:
                    raise TranscriptRequired('Automatic caption coverage or source-speech agreement failed. '
                                             'Review the source speech before using these captions.')
            origin = f'faster_whisper:{language}'
        except (ProcessingInterrupted, TranscriptRequired):
            raise
        except subprocess.TimeoutExpired as exc:
            raise TranscriptRequired('Automatic transcription timed out after 30 minutes. '
                                     'Provide timed SRT subtitles from the source audio to continue.') from exc
        except Exception as exc:
            raise TranscriptRequired('Automatic transcription unavailable. Run setup-transcription.ps1 '
                                     'and start the app with .venv/Scripts/python.exe. For the installed '
                                     'English model, select English; otherwise provide timed SRT subtitles.') from exc
    segments = validate_segments(segments, output['source_duration'])
    path = folder / 'transcript.json'
    path.write_text(json.dumps({'origin': origin, 'segments': segments}, ensure_ascii=False, indent=2),
                    encoding='utf-8')
    result = {'transcript_path': path.relative_to(storage).as_posix(), 'transcript_origin': origin,
              'transcript_sha256': file_hash(path)}
    if assessment is not None:
        result['caption_assessment'] = assessment
    return result


def srt_time(seconds):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    seconds, millis = divmod(millis, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{millis:03}'


def render(data, output, folder, storage):
    from clipping.captions import cues_for_window

    transcript = json.loads((storage / output['transcript_path']).read_text(encoding='utf-8'))
    segments = validate_segments(transcript['segments'], output['source_duration'])
    plan = output.get('selected_clip_plan') or data['clip_plan']
    start, duration = plan['start_seconds'], plan['duration_seconds']
    cues = [f"{index}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n"
            + '\n'.join(textwrap.wrap(cue['text'], width=48, break_long_words=False,
                                      break_on_hyphens=False)) + '\n'
            for index, cue in enumerate(cues_for_window(segments, start, duration), 1)]
    if not cues:
        raise ValueError('Transcript has no speech in the selected clip window; choose another start time')
    subtitles = folder / 'subtitles.srt'
    subtitles.write_text('\n'.join(cues), encoding='utf-8')
    width, height = {'9:16': (1080, 1920), '16:9': (1920, 1080), '1:1': (1080, 1080)}[plan['aspect_ratio']]
    caption_style = data.get('caption_style', DEFAULT_CAPTION_STYLE)
    subtitle_filter = "subtitles=subtitles.srt:force_style='FontSize=15,MarginV=48,MarginL=24,MarginR=24,Outline=2,Shadow=0,Alignment=2'"
    if caption_style != 'classic':
        from clipping.caption_styles import ass_for_window
        styled = folder / 'subtitles.ass'
        styled.write_text(ass_for_window(segments, start, duration, width, height, caption_style),
                          encoding='utf-8')
        subtitle_filter = 'subtitles=subtitles.ass'
    vf = (f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,'
          + subtitle_filter)
    framing = data.get('framing_mode', DEFAULT_FRAMING_MODE)
    filters = ['-vf', vf]
    if framing == 'fit':
        graph = (f'[0:v]split[background][foreground];'
                 f'[background]scale={width}:{height}:force_original_aspect_ratio=increase,'
                 f'crop={width}:{height},setsar=1,boxblur=24:2,eq=brightness=-0.12[blurred];'
                 f'[foreground]scale={width}:{height}:force_original_aspect_ratio=decrease:'
                 f'force_divisible_by=2,setsar=1[fullframe];'
                 f'[blurred][fullframe]overlay=(W-w)/2:(H-h)/2,{subtitle_filter}[composed]')
        filters = ['-filter_complex_threads', '1', '-filter_complex', graph,
                   '-map', '[composed]', '-map', '0:a:0']
    clip = folder / 'clip.mp4'
    from app.core.config import load_settings
    resources = load_settings().worker
    command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
             '-max_alloc', str(resources.memory_limit_mb * 1024 * 1024), '-ss', str(start),
             '-i', str(storage / output['source_path']), '-t', str(duration), *filters,
             '-c:v', 'libx264', '-threads', str(resources.cpu_threads), '-preset', 'fast', '-crf', '23',
             '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(clip)], cwd=folder)
    info = probe(clip)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), {})
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), {})
    actual_duration = float(info['format']['duration'])
    checks = {'dimensions': (video.get('width'), video.get('height')) == (width, height),
              'h264': video.get('codec_name') == 'h264', 'aac_audio': audio.get('codec_name') == 'aac',
              'duration': abs(actual_duration - duration) < 0.3, 'nonempty': clip.stat().st_size > 1024}
    if not all(checks.values()):
        raise ValueError(f'Clip quality checks failed: {checks}')
    from clipping.quality.validation import validate_media
    assessment = validate_media(clip, subtitles, duration=duration, aspect=plan['aspect_ratio'], info=info)
    if not assessment.passed:
        raise ValueError('Clip quality checks failed: ' + ', '.join(assessment.violations))
    result = {'clip_path': clip.relative_to(storage).as_posix(), 'clip_sha256': file_hash(clip),
              'subtitle_path': subtitles.relative_to(storage).as_posix(),
              'quality': {'checks': checks, 'width': width, 'height': height, 'duration': actual_duration}}
    result['quality_report'] = assessment.model_dump()
    if caption_style != 'classic':
        result.update(caption_style=caption_style,
                      styled_subtitle_path=styled.relative_to(storage).as_posix())
    if framing == 'fit':
        result['framing_mode'] = framing
    if caption_style == 'studio' and framing == 'fit' and plan['aspect_ratio'] == '9:16':
        result['render_template'] = TEMPLATE_ID
    return result
