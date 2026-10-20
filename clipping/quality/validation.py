"""Mechanical evidence; semantic accuracy and visual taste still need review."""

import math
import re
from fractions import Fraction

from pydantic import BaseModel, Field

from app.core.config import load_settings
from clipping import media


class QualityResult(BaseModel):
    passed: bool
    score: int
    checks: dict[str, bool]
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def result(checks, warnings=()):
    failures = [name for name, passed in checks.items() if not passed]
    return QualityResult(passed=not failures, score=round(100 * sum(checks.values()) / max(1, len(checks))),
                         checks=checks, violations=failures, warnings=list(warnings))


def validate_candidate(candidate, *, minimum=None, maximum=None, settings=None):
    settings = settings or load_settings()
    plan, quality = candidate.get('clip_plan', {}), candidate.get('quality', {})
    duration = plan.get('duration_seconds', 0)
    checks = {
        'duration': isinstance(duration, (int, float)) and not isinstance(duration, bool)
                    and math.isfinite(duration) and (minimum or settings.clips.min_duration) <= duration
                    <= (maximum or settings.clips.max_duration),
        'complete_thought': quality.get('completed_ending') is True,
        'sentence_opening': not quality.get('mid_sentence_opening', False),
        'standalone': not quality.get('context_dependent_opening', False),
        'no_advertising': not quality.get('promotional', False),
        'no_intro_outro': not quality.get('intro_or_outro', False),
        'speech_density': quality.get('speech_ratio', 0) >= settings.quality.minimum_speech_ratio,
        'speech_gaps': quality.get('largest_speech_gap', float('inf')) <= settings.quality.maximum_speech_gap,
    }
    return result(checks, ['Transcript boundaries are editorial evidence, not verified semantic completeness.'])


def interval_lengths(analysis, name, duration):
    starts = [float(value) for value in re.findall(r'lavfi\.' + name + r'_start=([\d.]+)', analysis)]
    ends = [float(value) for value in re.findall(r'lavfi\.' + name + r'_end=([\d.]+)', analysis)]
    return [max(0, min(duration, next((end for end in ends if end >= start), duration)) - start)
            for start in starts]


def analyze(clip):
    return media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-err_detect', 'explode', '-i', str(clip),
        '-af', 'silencedetect=noise=-50dB:d=0.5,ametadata=print:file=-,'
               'astats=metadata=1:reset=0,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-',
        '-vf', 'blackdetect=d=0.5:pix_th=0.10,metadata=print:file=-',
        '-f', 'null', '-'], timeout=180, kill_tree=True)


def validate_media(clip, subtitles, *, duration, aspect='9:16', info=None, analysis=None, settings=None):
    settings = settings or load_settings()
    if not clip.is_file() or not subtitles.is_file():
        return result({'files_present': False})
    try:
        info = info if info is not None else media.probe(clip)
        analysis = analysis if analysis is not None else analyze(clip)
        actual = float(info['format']['duration'])
        video = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), {})
        audio = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), {})
        rate = float(Fraction(video.get('avg_frame_rate') or video.get('r_frame_rate') or '0/1'))
        text = subtitles.read_text(encoding='utf-8')
        cues = media.parse_srt(text)
        display_blocks = [block.splitlines()[2:] for block in re.split(r'\r?\n\s*\r?\n', text.strip())]
        levels = re.findall(r'lavfi\.astats\.Overall\.RMS_level=([^\s]+)', analysis)
        rms = float(levels[-1]) if levels else float('-inf')
        size = {'9:16': (1080, 1920), '16:9': (1920, 1080), '1:1': (1080, 1080)}[aspect]
        checks = {
            'file_size': 1024 <= clip.stat().st_size <= 150 * 1024 * 1024,
            'full_decode': True,
            'video': bool(video), 'audio': bool(audio),
            'resolution': (video.get('width'), video.get('height')) == size,
            'duration': math.isfinite(actual) and abs(actual - duration) <= settings.quality.duration_tolerance,
            'fps': settings.quality.minimum_fps <= rate <= settings.quality.maximum_fps,
            'audible_audio': math.isfinite(rms) and rms > settings.quality.minimum_audio_db,
            'no_black_frames': max(interval_lengths(analysis, 'black', actual), default=0)
                               < settings.quality.maximum_black_seconds,
            'no_excessive_silence': sum(interval_lengths(analysis, 'silence', actual)) / max(actual, .001)
                                    <= settings.quality.maximum_silence_ratio,
            'captions': bool(cues) and all(0 <= c['start'] < c['end'] <= actual + .05 for c in cues),
            'subtitle_bounds': bool(display_blocks) and all(1 <= len(lines) <= 2 and
                all(len(line) <= settings.quality.maximum_subtitle_chars for line in lines) for lines in display_blocks),
        }
        return result(checks, ['Source-speech accuracy requires independent timed cues and human review.'])
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError):
        return result({'probe_decode_and_subtitles': False})
