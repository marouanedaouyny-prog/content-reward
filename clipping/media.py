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


class SourceFailure(Exception):
    """A source failure with bounded diagnostic fields safe for saved state."""

    default_reason = 'downloader_setup_failed'
    reasons = frozenset({'network_unavailable', 'http_unavailable', 'rate_limited',
                         'proxy_unavailable', 'dns_unavailable', 'timeout',
                         'tls_verification_failed', 'downloader_setup_failed', 'access_refused'})

    def __init__(self, message, *, reason=None, http_status=None, timeout_seconds=None):
        super().__init__(message)
        self.diagnostic = {'reason': reason if isinstance(reason, str) and reason in self.reasons else self.default_reason}
        if type(http_status) is int and 100 <= http_status <= 599:
            self.diagnostic['http_status'] = http_status
        if (type(timeout_seconds) in (int, float) and math.isfinite(timeout_seconds)
                and 0 < timeout_seconds <= 86400):
            self.diagnostic['timeout_seconds'] = timeout_seconds


class SourceUnavailable(SourceFailure):
    """A temporary network failure, eligible for a saved automatic retry."""

    default_reason = 'network_unavailable'


class SourceAccessRequired(SourceFailure):
    """A source-specific refusal; another researched source may be usable."""

    default_reason = 'access_refused'


class SourceSetupRequired(SourceFailure):
    """A local downloader or TLS problem that must not retire a selected source."""


def classify_source_failure(error):
    """Classify provider output without persisting messages, URLs or arguments."""
    timed_out = isinstance(error, subprocess.TimeoutExpired)
    detail = error.stderr if timed_out else str(error)
    if isinstance(detail, bytes):
        detail = detail.decode('utf-8', errors='replace')
    detail = str(detail or '').lower()
    detail = re.sub(r'https?://\S+', '', detail[:4096] + detail[-4096:])
    match = re.search(r'\b(?:http(?:\s+error)?|server returned)\s*:?\s*([45]\d{2})\b', detail)
    status = int(match.group(1)) if match else None
    diagnostic = {'http_status': status, 'timeout_seconds': error.timeout if timed_out else None}
    if any(term in detail for term in ('certificate_verify_failed', 'certificate verify failed',
                                       'certificate verification failed', 'ssl certificate problem')):
        kind, reason = SourceSetupRequired, 'tls_verification_failed'
    elif status == 429:
        kind, reason = SourceUnavailable, 'rate_limited'
    elif status is not None and (status >= 500 or status in (408, 425)):
        kind, reason = SourceUnavailable, 'http_unavailable'
    elif any(term in detail for term in ('unable to connect to proxy', 'proxy error', 'proxyerror',
                                         'tunnel connection failed', 'could not resolve proxy', 'proxyconnect tcp')):
        kind, reason = SourceUnavailable, 'proxy_unavailable'
    elif timed_out or 'timed out' in detail or re.search(r'\btimeout\b', detail):
        kind, reason = SourceUnavailable, 'timeout'
    elif any(term in detail for term in ('name resolution', 'getaddrinfo failed', 'name or service not known',
                                         'could not resolve hostname', 'nodename nor servname')):
        kind, reason = SourceUnavailable, 'dns_unavailable'
    elif any(term in detail for term in ('connection refused', '10061', 'temporary failure',
                                         'connection reset', 'network is unreachable')):
        kind, reason = SourceUnavailable, 'network_unavailable'
    elif status is not None or any(term in detail for term in ('private video', 'video is private',
            'video unavailable', 'video is unavailable', 'video has been removed',
            'sign in to confirm', 'not available in your country',
            'members-only', 'copyright', 'requested format is not available', 'no video formats found')):
        kind, reason = SourceAccessRequired, 'access_refused'
    else:
        kind, reason = SourceSetupRequired, 'downloader_setup_failed'
    messages = {SourceSetupRequired: 'Source downloader setup requires correction; selected moments are saved.',
                SourceUnavailable: 'Source connection temporarily unavailable; section progress is saved.',
                SourceAccessRequired: 'Public captions or partial media are unavailable for this source.'}
    return kind(messages[kind], reason=reason, **diagnostic)


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
    process = None
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
                    partial_stderr = None
                    while True:
                        if should_stop and should_stop():
                            raise ProcessingInterrupted('Processing paused or cancelled')
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(args, timeout, stderr=partial_stderr)
                        try:
                            stdout, stderr = process.communicate(timeout=min(.5, remaining))
                            break
                        except subprocess.TimeoutExpired as exc:
                            partial_stderr = exc.stderr[-8192:] if exc.stderr else partial_stderr
                            continue
                except (subprocess.TimeoutExpired, ProcessingInterrupted):
                    if os.name != 'nt':
                        terminate_process(process)
                    raise
                result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            # Managed context exit has terminated the tree and drained its pipes.
            # Windows does not expose partial communicate() buffers until EOF.
            _, stderr = process.communicate(timeout=10)
            if stderr:
                exc.stderr = stderr[-8192:]
        raise
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
        validate_confidence(segment, [('avg_logprob', None, 0), ('no_speech_prob', 0, 1),
                                      ('compression_ratio', 0, None)])
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
                validate_confidence(word, [('probability', 0, 1)])
                previous_end = word_end
            if ' '.join(''.join(word['word'] for word in words).split()) != ' '.join(text.split()):
                raise ValueError('Word text must match its transcript segment')
    return sorted(segments, key=lambda s: (s['start'], s['end']))


def validate_confidence(record, fields):
    for name, minimum, maximum in fields:
        if name not in record:
            continue
        value = record[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or minimum is not None and value < minimum or maximum is not None and value > maximum):
            raise ValueError('Transcription confidence diagnostics must be finite numbers within their valid range')


def model_files_ready(folder):
    return all((folder / name).is_file() and (folder / name).stat().st_size > 0
               for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'))


def whisper_model_location(storage, language=None):
    from app.repositories.store import Store as _Store
    if isinstance(storage, _Store):
        storage = storage.path.parent
    elif not isinstance(storage, Path):
        storage = Path(storage).parent
    english = isinstance(language, str) and language.split('-', 1)[0].casefold() == 'en'
    from app.core.config import load_settings
    configured = load_settings().whisper.model
    if Path(configured).name.casefold().endswith('.en') and not english:
        configured = 'small'
    local = storage / 'models' / configured
    if model_files_ready(local):
        return str(local)
    direct = Path(configured).expanduser()
    return str(direct) if model_files_ready(direct) else configured


def asr_confidence(segments, origin, model=None):
    """Summarize available model diagnostics without interpreting them as truth."""
    automatic = origin.startswith('faster_whisper:')
    segment_count = sum(any(field in segment for field in
                            ('avg_logprob', 'no_speech_prob', 'compression_ratio')) for segment in segments)
    words = [word for segment in segments for word in segment.get('words', [])]
    probability_count = sum('probability' in word for word in words)
    return {'available': automatic and bool(segment_count or probability_count),
            'origin': origin, 'model': model, 'segment_count': len(segments),
            'segments_with_diagnostics': segment_count, 'word_count': len(words),
            'words_with_probability': probability_count, 'speech_accuracy': 'not_verified',
            'limitations': ['Recognition confidence is a model diagnostic, not verified speech accuracy.',
                            'Missing confidence is unknown; high confidence does not verify names or quotations.',
                            'Values from different models and decoding settings are not directly comparable.']}


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
    model = None
    if data.get('transcript_srt') or data.get('transcript'):
        segments = data.get('transcript') or parse_srt(data['transcript_srt'])
        origin = 'operator_supplied_practice' if data['dry_run'] else 'operator_supplied'
    elif data['dry_run']:
        segments = [{'start': 0, 'end': output['source_duration'],
                     'text': 'Practice clip. No publication or reward submission.'}]
        origin = 'synthetic_practice'
    else:
        try:
            from app.core.config import load_settings
            settings = load_settings()
            model = whisper_model_location(storage, data.get('language'))
            args = [sys.executable, '-I', str(Path(__file__).with_name('_transcribe.py')),
                    str(storage / output['source_path']),
                    model, str(storage / 'models'),
                    '--device', settings.whisper.device, '--cpu-threads', str(settings.worker.cpu_threads)]
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
    path.write_text(json.dumps({'origin': origin, 'segments': segments,
                               'asr_confidence': asr_confidence(segments, origin, model)},
                              ensure_ascii=False, indent=2, allow_nan=False),
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
    from app.core.config import load_settings
    settings = load_settings()
    window_cues = cues_for_window(segments, start, duration, settings=settings)
    if not window_cues:
        raise ValueError('Transcript has no speech in the selected clip window; choose another start time')
    # PRD-GROWTH section 9: opt-in silence removal keeps captions synchronized.
    silence_plan = None
    if settings.silence.aggressive_cut:
        from clipping import silence
        silence_plan = silence.plan_removal(
            duration, silence.detect(storage / output['source_path'], start, duration, settings=settings))
        if silence_plan['applied']:
            window_cues = silence.remap_cues(window_cues, silence_plan['gaps'])
    effective_duration = (duration - silence_plan['removed_seconds']
                          if silence_plan and silence_plan['applied'] else duration)
    cues = [f"{index}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n"
            + '\n'.join(textwrap.wrap(cue['text'], width=48, break_long_words=False,
                                      break_on_hyphens=False)) + '\n'
            for index, cue in enumerate(window_cues, 1)]
    subtitles = folder / 'subtitles.srt'
    subtitles.write_text('\n'.join(cues), encoding='utf-8')
    width, height = {'9:16': (1080, 1920), '16:9': (1920, 1080), '1:1': (1080, 1080)}[plan['aspect_ratio']]
    caption_style = data.get('caption_style', DEFAULT_CAPTION_STYLE)
    subtitle_filter = "subtitles=subtitles.srt:force_style='FontSize=15,MarginV=48,MarginL=24,MarginR=24,Outline=2,Shadow=0,Alignment=2'"
    time_map = None
    if silence_plan and silence_plan['applied']:
        from clipping import silence
        time_map = silence.time_map(silence_plan['gaps'])
    if caption_style != 'classic':
        from clipping.caption_styles import ass_for_window
        styled = folder / 'subtitles.ass'
        styled.write_text(ass_for_window(segments, start, duration, width, height, caption_style,
                                         settings=settings, time_map=time_map), encoding='utf-8')
        subtitle_filter = 'subtitles=subtitles.ass'
    vf = (f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,'
          + subtitle_filter)
    framing = data.get('framing_mode', DEFAULT_FRAMING_MODE)
    framing_eff = framing
    focus_report = None
    if framing == 'speaker-focus':
        # PRD-GROWTH section 12: speaker-focus only when a stable face is
        # reliable; otherwise the export falls back to the fit template.
        from clipping import framing as framing_analysis
        focus_report = framing_analysis.analyze(storage / output['source_path'], start, duration,
                                                plan['aspect_ratio'])
        framing_eff = 'speaker-focus' if focus_report['crop'] else 'fit'
        if focus_report['crop']:
            crop_x, crop_y, crop_w, crop_h = focus_report['crop']
            vf = (f'crop={crop_w}:{crop_h}:{crop_x}:{crop_y},'
                  f'scale={width}:{height},setsar=1,' + subtitle_filter)
    filters = ['-vf', vf]
    if framing_eff == 'fit':
        graph = (f'[0:v]split[background][foreground];'
                 f'[background]scale={width}:{height}:force_original_aspect_ratio=increase,'
                 f'crop={width}:{height},setsar=1,boxblur=24:2,eq=brightness=-0.12[blurred];'
                 f'[foreground]scale={width}:{height}:force_original_aspect_ratio=decrease:'
                 f'force_divisible_by=2,setsar=1[fullframe];'
                 f'[blurred][fullframe]overlay=(W-w)/2:(H-h)/2,{subtitle_filter}[composed]')
        filters = ['-filter_complex_threads', '1', '-filter_complex', graph,
                   '-map', '[composed]', '-map', '0:a:0']
    if silence_plan and silence_plan['applied']:
        kept = silence_plan['kept']
        graph = ''.join(f'[0:v]trim=start={begin:g}:end={finish:g},setpts=PTS-STARTPTS[v{index}];'
                        f'[0:a]atrim=start={begin:g}:end={finish:g},asetpts=PTS-STARTPTS[a{index}];'
                        for index, (begin, finish) in enumerate(kept))
        graph += ''.join(f'[v{index}][a{index}]' for index in range(len(kept))) \
                 + f'concat=n={len(kept)}:v=1:a=1[cutv][cuta];'
        if framing_eff == 'fit':
            graph += ('[cutv]split[background][foreground];'
                      f'[background]scale={width}:{height}:force_original_aspect_ratio=increase,'
                      f'crop={width}:{height},setsar=1,boxblur=24:2,eq=brightness=-0.12[blurred];'
                      f'[foreground]scale={width}:{height}:force_original_aspect_ratio=decrease:'
                      f'force_divisible_by=2,setsar=1[fullframe];'
                      f'[blurred][fullframe]overlay=(W-w)/2:(H-h)/2,{subtitle_filter}[composed]')
        else:
            graph += (f'[cutv]scale={width}:{height}:force_original_aspect_ratio=increase,'
                      f'crop={width}:{height},setsar=1,{subtitle_filter}[composed]')
        filters = ['-filter_complex_threads', '1', '-filter_complex', graph,
                   '-map', '[composed]', '-map', '[cuta]']
    clip = folder / 'clip.mp4'
    resources = settings.worker
    from clipping.encoding import encoder_options
    encoding = encoder_options(settings.video.encoder_profile)
    command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
             '-max_alloc', str(resources.memory_limit_mb * 1024 * 1024), '-ss', str(start),
             '-i', str(storage / output['source_path']), '-t', f'{effective_duration:g}', *filters,
             '-c:v', 'libx264', '-threads', str(resources.cpu_threads), '-preset', encoding['preset'],
             '-crf', str(encoding['crf']),
             '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(clip)], cwd=folder)
    info = probe(clip)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), {})
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), {})
    actual_duration = float(info['format']['duration'])
    checks = {'dimensions': (video.get('width'), video.get('height')) == (width, height),
              'h264': video.get('codec_name') == 'h264', 'aac_audio': audio.get('codec_name') == 'aac',
              'duration': abs(actual_duration - effective_duration) < 0.3, 'nonempty': clip.stat().st_size > 1024}
    if not all(checks.values()):
        raise ValueError(f'Clip quality checks failed: {checks}')
    from clipping.quality.validation import validate_media
    assessment = validate_media(clip, subtitles, duration=effective_duration, aspect=plan['aspect_ratio'], info=info)
    if not assessment.passed:
        raise ValueError('Clip quality checks failed: ' + ', '.join(assessment.violations))
    result = {'clip_path': clip.relative_to(storage).as_posix(), 'clip_sha256': file_hash(clip),
              'subtitle_path': subtitles.relative_to(storage).as_posix(),
              'subtitle_sha256': file_hash(subtitles),
              'quality': {'checks': checks, 'width': width, 'height': height, 'duration': actual_duration,
                          'encoder_profile': settings.video.encoder_profile,
                          'encoder_preset': encoding['preset'], 'encoder_crf': encoding['crf']}}
    if silence_plan is not None:
        from clipping import silence
        result['silence_removal'] = {**silence_plan, 'note': silence.NOTE}
        if silence_plan['applied']:
            result['render_duration_seconds'] = round(effective_duration, 3)
    result['quality_report'] = assessment.model_dump()
    if caption_style != 'classic':
        result.update(caption_style=caption_style,
                      styled_subtitle_path=styled.relative_to(storage).as_posix(),
                      styled_subtitle_sha256=file_hash(styled))
    if focus_report is not None:
        result['speaker_focus'] = focus_report
        if framing_eff == 'fit':
            result['framing_fallback'] = {'requested': 'speaker-focus', 'used': 'fit',
                                          'reason': focus_report['reason']}
    if framing_eff in ('fit', 'speaker-focus'):
        result['framing_mode'] = framing_eff
    if caption_style == 'studio' and framing_eff == 'fit' and plan['aspect_ratio'] == '9:16':
        result['render_template'] = TEMPLATE_ID
    return result
