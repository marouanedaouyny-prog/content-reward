"""Detect missing or repeated ASR captions against the selected source speech.

These gates catch gross omissions and hallucinated loops. Agreement with public
captions and timing coverage do not establish perfect transcription accuracy.
"""

import math
import re
from collections import Counter
from difflib import SequenceMatcher


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


def _agreement(expected, observed):
    shared = sum((Counter(expected) & Counter(observed)).values())
    ordered = sum(block.size for block in
                  SequenceMatcher(None, expected, observed, autojunk=False).get_matching_blocks())
    return (shared / max(1, len(expected)), shared / max(1, len(observed)),
            ordered / max(1, len(expected)))


def _timed_rows(cues, start, end):
    rows = []
    for cue in cues:
        word_timed = isinstance(cue.get('words'), list)
        for row in cue['words'] if word_timed else [cue]:
            begin, finish = row.get('start'), row.get('end')
            if not _finite(begin) or not _finite(finish) or finish <= begin:
                continue
            if begin >= end or finish <= start:
                continue
            words = _tokens(row.get('word', row.get('text', '')))
            if words:
                rows.append({'start': begin, 'end': finish, 'words': words, 'word_timed': word_timed,
                             'raw_words': [row] if word_timed else []})
    return rows


def _local_agreement(segments, reference, start, end):
    observed = _timed_rows(segments, start, end)
    checks = []
    for cue in reference:
        begin, finish = cue.get('start'), cue.get('end')
        if not _finite(begin) or not _finite(finish):
            continue
        begin, finish = max(start, begin), min(end, finish)
        if finish <= begin:
            continue
        _, expected = _evidence([cue], begin, finish)
        # Tiny fragments and names alone cannot establish a local disagreement.
        if len(expected) < 6:
            continue
        # Public cue boundaries and ASR word timings are approximate. Cue-only
        # transcripts use their supplied midpoint, never invented word timings.
        actual = [word for row in observed
                  if begin - .75 <= (row['start'] + row['end']) / 2 <= finish + .75
                  for word in row['words']]
        recall, _, ordered_recall = _agreement(expected, actual)
        checks.append({'start': round(begin, 3), 'end': round(finish, 3),
                       'reference_word_count': len(expected), 'caption_word_count': len(actual),
                       'source_token_recall': round(recall, 6),
                       'ordered_token_recall': round(ordered_recall, 6),
                       # A matching whole clip must not hide one substantially
                       # mistranscribed passage. Use the same recall/order
                       # minimums as the whole-window check for each sizable cue.
                       'passed': recall >= .65 and ordered_recall >= .6})
    return {'evaluated': len(checks), 'failed': sum(not check['passed'] for check in checks),
            'timing_tolerance_seconds': .75, 'checks': checks}


def _timing_confidence(word_timed, rows_words):
    """Return the weakest word probability in one timed row.

    ``None`` means the wording data carries no model confidence, so the row's
    timing cannot be called unreliable. Local models always emit probabilities;
    other cue sources may not.
    """
    if not word_timed:
        return None
    probabilities = [word.get('probability') for word in rows_words]
    if not probabilities or any(not _finite(p) for p in probabilities):
        return None
    return min(probabilities)


def _boundary_words(segments, start, end):
    fragments = []
    for row in _timed_rows(segments, start, end):
        if not row['word_timed']:
            continue
        # A few milliseconds of alignment jitter is normal. A word extending
        # substantially into the context padding needs the clip boundary reviewed.
        edge = ('leading' if start - row['start'] > .2 + 1e-6 else
                'trailing' if row['end'] - end > .2 + 1e-6 else None)
        if not edge:
            continue
        # Local ASR word timing jitters by roughly ±0.2–0.35 s, and the model
        # marks unreliable timings with low word probability. A shallow crossing
        # with weak timing confidence cannot prove a clipped word; a deep cut
        # into one word, or a confidently timed crossing, still needs review.
        depth = start - row['start'] if edge == 'leading' else row['end'] - end
        confidence = _timing_confidence(True, row['raw_words'])
        if depth <= .35 and confidence is not None and confidence < .7:
            continue
        fragments.append({'edge': edge, 'text': ' '.join(row['words']),
                          'start': row['start'], 'end': row['end']})
    return fragments


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
    recall, precision, ordered_recall = _agreement(expected_words, observed_words)
    coverage = intersection / expected_seconds if expected_seconds else 0
    repeated = _excess_repetition(observed_words, expected_words)
    local = _local_agreement(segments, reference, start, end)
    boundary_words = _boundary_words(segments, start, end)
    failures = []
    if not expected_words:
        failures.append('missing_reference')
    if not observed_words:
        failures.append('missing_captions')
    if expected_words and recall < .65:
        failures.append('insufficient_reference_text')
    if observed_words and precision < .6:
        failures.append('unsupported_caption_text')
    if expected_words and ordered_recall < .6:
        failures.append('source_word_order')
    if expected_words and coverage < .6:
        failures.append('insufficient_speech_coverage')
    if local['failed']:
        failures.append('timed_source_disagreement')
    if boundary_words:
        failures.append('clipped_boundary_word')
    if repeated:
        failures.append('excessive_repetition')
    return {'passed': not failures, 'failures': failures,
            'caption_fraction': round(observed_seconds / duration, 6),
            'expected_speech_fraction': round(expected_seconds / duration, 6),
            'speech_caption_intersection_fraction': round(intersection / duration, 6),
            'expected_speech_coverage': round(coverage, 6),
            'source_token_recall': round(recall, 6),
            'source_token_precision': round(precision, 6),
            'ordered_token_recall': round(ordered_recall, 6),
            'local_source_checks': local, 'boundary_words': boundary_words,
            'reference_word_count': len(expected_words), 'caption_word_count': len(observed_words),
            'excess_repetition': repeated, 'speech_accuracy': 'not_verified',
            'limitations': ['Public source captions can contain recognition errors.',
                            'Coarse cue timing can require local review despite matching wording.',
                            'Token and timing agreement do not verify names, meaning or audio accuracy.']}
