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


def validate_candidate(candidate, *, minimum=None, maximum=None, settings=None, strict=False):
    from clipping.planning import (INTRO_OUTRO, PROMOTION, host_meta_setup, opening_context,
                                   speech_text, standalone_boundary_checks)
    settings = settings or load_settings()
    plan, quality = candidate.get('clip_plan', {}), candidate.get('quality', {})
    features = candidate.get('transcript_features') or {}
    text = speech_text(candidate.get('source_excerpt') or '')
    duration = plan.get('duration_seconds', 0)
    ratio, gap = quality.get('speech_ratio'), quality.get('largest_speech_gap')
    unanswered = (quality.get('ending_question') is True or features.get('ending_question') is True
                  or bool(re.search(r'''\?["'\u201d\u2019)]*$''', text)))
    checks = {
        'duration': isinstance(duration, (int, float)) and not isinstance(duration, bool)
                    and math.isfinite(duration) and (minimum or settings.clips.min_duration) <= duration
                    <= (maximum or settings.clips.max_duration),
        'complete_thought': quality.get('completed_ending') is True,
        'answered_ending': not unanswered,
        'no_mid_sentence_start': not quality.get('mid_sentence_opening', False),
        'no_mid_sentence_end': not quality.get('filler_opening', False),
        'standalone': not quality.get('context_dependent_opening', False)
                      and (not text or not opening_context(text)),
        'no_advertising': not quality.get('promotional', False) and not PROMOTION.search(text),
        'no_intro_outro': not quality.get('intro_or_outro', False) and not INTRO_OUTRO.search(text),
        'no_host_setup': not quality.get('host_meta_setup', False) and not host_meta_setup(text),
        'speech_density': isinstance(ratio, (int, float)) and not isinstance(ratio, bool)
                          and math.isfinite(ratio) and settings.quality.minimum_speech_ratio <= ratio <= 1,
        'speech_gaps': isinstance(gap, (int, float)) and not isinstance(gap, bool)
                       and math.isfinite(gap) and 0 <= gap <= settings.quality.maximum_speech_gap,
    }
    if strict:
        checks.update(standalone_boundary_checks(text))
        flags = ('completed_ending', 'filler_opening', 'context_dependent_opening',
                 'mid_sentence_opening', 'promotional', 'intro_or_outro', 'host_meta_setup')
        ending_evidence = quality.get('ending_question', features.get('ending_question'))
        checks['transcript_structure_evidence'] = (bool(text) and isinstance(ending_evidence, bool)
            and all(isinstance(quality.get(key), bool) for key in flags))
    failures = [name for name, passed in checks.items() if not passed]
    return QualityResult(passed=not failures, score=round(100 * sum(checks.values()) / max(1, len(checks))),
                         checks=checks, violations=failures,
                         warnings=['Transcript boundaries are editorial evidence, not verified semantic completeness.'])


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
        return QualityResult(passed=False, score=0, checks={}, violations=['clip or subtitle file missing'],
                             warnings=[])
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
        failures = [name for name, passed in checks.items() if not passed]
        return QualityResult(passed=not failures, score=round(100 * sum(checks.values()) / max(1, len(checks))),
                             checks=checks, violations=failures,
                             warnings=['Source-speech accuracy requires independent timed cues and human review.'])
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as e:
        return QualityResult(passed=False, score=0, checks={}, violations=[str(e)], warnings=[])
