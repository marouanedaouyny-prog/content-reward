"""Config-driven pause detection and opt-in removal planning for one clip window.

Removal is enabled only by the explicit ``silence.aggressive_cut`` setting
(PRD-GROWTH section 9 defaults it to false). Detected pauses are measured with
ffmpeg silencedetect at the configured threshold; micro-pauses below
``min_duration_ms`` are never touched. Removal plans are time maps applied to
caption cues so subtitles stay synchronized with the shortened audio.
"""

import re

from clipping import media

NOTE = ('Silence removal is detection-based (ffmpeg silencedetect at the '
        'configured threshold); speech naturalness still needs human review.')


def detect(source_path, start, duration, settings=None):
    """Return silence gaps in window-relative seconds for one clip window."""
    from app.core.config import load_settings
    settings = settings or load_settings()
    config = settings.silence
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (start, duration)):
        raise ValueError('Silence detection requires finite window boundaries')
    # silencedetect reports through frame metadata; ametadata prints it on stdout.
    analysis = media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error',
        '-ss', f'{start:g}', '-t', f'{duration:g}', '-i', str(source_path),
        '-af', f'silencedetect=noise={config.threshold_db}dB:d={config.min_duration_ms / 1000:g},'
               'ametadata=print:file=-',
        '-f', 'null', '-'], timeout=180, kill_tree=True)
    starts = [float(value) for value in re.findall(r'silence_start=([\d.]+)', analysis)]
    ends = [float(value) for value in re.findall(r'silence_end=([\d.]+)', analysis)]
    minimum = config.min_duration_ms / 1000
    gaps = []
    for index, gap_start in enumerate(starts):
        # A silence without an end marker runs to the end of the window.
        gap_end = ends[index] if index < len(ends) else duration
        gap_start, gap_end = max(0.0, gap_start), min(duration, gap_end)
        if gap_end - gap_start >= minimum:
            gaps.append((round(gap_start, 3), round(gap_end, 3)))
    return gaps


def plan_removal(duration, gaps):
    """Build a conservative removal plan; too much silence refuses the cut.

    Returns ``{'gaps', 'kept', 'removed_seconds', 'applied', 'reason'}``. The
    plan is never partially applied: either every listed gap is removed or the
    window keeps its original duration.
    """
    minimum, ratio_cap = 0.1, 0.3
    cleaned = []
    for gap_start, gap_end in gaps:
        gap_start, gap_end = max(0.0, gap_start), min(duration, gap_end)
        if gap_end - gap_start > 0 and gap_start < gap_end:
            cleaned.append((gap_start, gap_end))
    cleaned.sort()
    merged = []
    for gap_start, gap_end in cleaned:
        if merged and gap_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(gap_end, merged[-1][1]))
        else:
            merged.append((gap_start, gap_end))
    removed = sum(gap_end - gap_start for gap_start, gap_end in merged)
    if not merged:
        return {'applied': False, 'gaps': [], 'kept': [(0.0, duration)],
                'removed_seconds': 0.0, 'reason': 'no_detected_pauses'}
    if removed / duration > ratio_cap:
        return {'applied': False, 'gaps': [], 'kept': [(0.0, duration)],
                'removed_seconds': 0.0, 'reason': 'too_much_detected_silence'}
    kept, cursor = [], 0.0
    for gap_start, gap_end in merged:
        if gap_start - cursor >= minimum:
            kept.append((cursor, gap_start))
        cursor = max(cursor, gap_end)
    if duration - cursor >= minimum:
        kept.append((cursor, duration))
    if not kept:
        return {'applied': False, 'gaps': [], 'kept': [(0.0, duration)],
                'removed_seconds': 0.0, 'reason': 'window_became_all_silence'}
    return {'applied': True, 'gaps': merged, 'kept': kept,
            'removed_seconds': round(removed, 3), 'reason': 'detected_pauses_removed'}


def time_map(gaps):
    """Monotonic window-relative time map that subtracts removed gaps."""
    def mapped(value):
        removed = sum(min(max(0.0, value - gap_start), gap_end - gap_start)
                      for gap_start, gap_end in gaps)
        return round(value - removed, 3)
    return mapped


def remap_cues(cues, gaps):
    """Shift caption cues through a removal plan; text is never changed."""
    mapped = time_map(gaps)
    return [{**cue, 'start': mapped(cue['start']), 'end': mapped(cue['end'])} for cue in cues]
