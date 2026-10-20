"""Detect missing or repeated ASR captions against the selected source speech.

These gates catch gross omissions and hallucinated loops. Agreement with public
captions and timing coverage do not establish perfect transcription accuracy.
"""

import math
import re
from collections import Counter


def _tokens(text):
    text = re.sub(r'\[[^\]]*\]', ' ', str(text)).replace('’', "'")
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _evidence(cues, start, end):
    intervals, words = [], []
    for cue in cues:
        rows = cue.get('words') if isinstance(cue.get('words'), list) else [cue]
        for row in rows:
            begin, finish = row.get('start'), row.get('end')
            if not _finite(begin) or not _finite(finish) or finish <= begin:
                continue
            begin, finish = max(start, begin), min(end, finish)
            if begin >= finish:
                continue
            tokens = _tokens(row.get('word', row.get('text', '')))
            if tokens:
                intervals.append((begin, finish))
                words.extend(tokens)
    return _merge(intervals), words


def _intersection(first, second):
    seconds, left, right = 0, 0, 0
    while left < len(first) and right < len(second):
        a, b = first[left], second[right]
        seconds += max(0, min(a[1], b[1]) - max(a[0], b[0]))
        if a[1] <= b[1]:
            left += 1
        else:
            right += 1
    return seconds


def _excess_repetition(words, reference):
    def phrases(values):
        return Counter(tuple(values[index:index + 4]) for index in range(len(values) - 3))

    expected = phrases(reference)
    return any(count >= 3 and count > expected[phrase] + 2
               and (count - expected[phrase]) * 4 / max(1, len(words)) >= .3
               for phrase, count in phrases(words).items())


def assess_captions(segments, start, duration, reference):
    """Compare captions and local-time source cues within one selected window.

    ``reference`` is a list of ``{start, end, text}`` cues in the same timebase
    as ``segments``. Word timestamps, when present, determine which spoken words
    belong to the window. Natural silence is measured against reference speech,
    rather than requiring captions throughout the entire video.
    """
    if not _finite(start) or not _finite(duration) or start < 0 or duration <= 0:
        raise ValueError('Caption review requires a finite positive source window')
    if not isinstance(segments, list) or not isinstance(reference, list):
        raise ValueError('Caption review requires transcript and reference cue lists')
    if any(not isinstance(cue, dict) for cue in [*segments, *reference]):
        raise ValueError('Caption review cues must be objects')
    end = start + duration
    observed_intervals, observed_words = _evidence(segments, start, end)
    expected_intervals, expected_words = _evidence(reference, start, end)
    observed_seconds = sum(finish - begin for begin, finish in observed_intervals)
    expected_seconds = sum(finish - begin for begin, finish in expected_intervals)
    intersection = _intersection(observed_intervals, expected_intervals)
    expected_counts, observed_counts = Counter(expected_words), Counter(observed_words)
    recall = sum((expected_counts & observed_counts).values()) / max(1, len(expected_words))
    coverage = intersection / expected_seconds if expected_seconds else 0
    repeated = _excess_repetition(observed_words, expected_words)
    failures = []
    if not expected_words:
        failures.append('missing_reference')
    if not observed_words:
        failures.append('missing_captions')
    if expected_words and (recall < .45 or len(observed_words) < len(expected_words) * .4):
        failures.append('insufficient_reference_text')
    if expected_words and coverage < .35:
        failures.append('insufficient_speech_coverage')
    if repeated:
        failures.append('excessive_repetition')
    return {'passed': not failures, 'failures': failures,
            'caption_fraction': round(observed_seconds / duration, 6),
            'expected_speech_fraction': round(expected_seconds / duration, 6),
            'speech_caption_intersection_fraction': round(intersection / duration, 6),
            'expected_speech_coverage': round(coverage, 6),
            'source_token_recall': round(recall, 6),
            'reference_word_count': len(expected_words), 'caption_word_count': len(observed_words),
            'excess_repetition': repeated, 'speech_accuracy': 'not_verified'}
