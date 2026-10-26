"""Build readable caption cues from validated transcript timing."""

import re
import textwrap

# PRD-GROWTH sections 10 and 16: display-only cleanup of zero-meaning
# disfluencies. Audio and source transcripts are never modified, and words that
# carry meaning ("like", "you know", "basically") are deliberately kept.
FILLER_TOKENS = frozenset({'uh', 'um'})


def display_text(text):
    """Remove standalone uh/um disfluencies from displayed caption text."""
    value = re.sub(r'\b(?:uh|um)\.{2,}', ' ', str(text), flags=re.IGNORECASE)
    value = re.sub(r'\b(?:uh|um)\b[,;:]?', ' ', value, flags=re.IGNORECASE)
    value = re.sub(r'\s+([.,!?])', r'\1', value)
    value = re.sub(r'^\s*[.,!?]+\s*', '', value)
    return ' '.join(value.split())


def filler_word(word):
    """True when a timed ASR word carries only a uh/um disfluency."""
    return re.sub(r'[^a-z]', '', str(word).lower()) in FILLER_TOKENS


def phrase_text(words):
    # The aligner supplies spaces where the language needs them.
    return ' '.join(''.join(word['word'] for word in words).split())


def wrap_phrase(text):
    # Leave room for the renderer's proportional font and horizontal margins.
    return '\n'.join(textwrap.wrap(text, width=16, break_long_words=False,
                                   break_on_hyphens=False))


def caption_words(words):
    """Keep zero-length ASR words with a neighbor that has usable timing."""
    timed, pending, pending_start = [], '', None
    for word in words:
        if word['start'] == word['end']:
            pending += word['word']
            if pending_start is None:
                pending_start = word['start']
            continue
        value = dict(word)
        if pending:
            value['word'] = pending + value['word']
            value['start'] = min(pending_start, value['start'])
            pending, pending_start = '', None
        timed.append(value)
    if pending and timed:
        timed[-1]['word'] += pending
        timed[-1]['end'] = max(timed[-1]['end'], words[-1]['end'])
    return timed


def cues_for_window(segments, start, duration, *, settings=None):
    from app.core.config import load_settings
    settings = settings or load_settings()
    captions = settings.captions
    remove_fillers = captions.remove_fillers
    end = start + duration
    cues = []

    def append_cue(cue_start, cue_end, text):
        if text.strip() and cue_start < end and cue_end > start:
            cues.append({'start': max(0, cue_start - start),
                         'end': min(duration, cue_end - start), 'text': text})

    for segment in segments:
        original_words = segment.get('words') or []
        window_words = [word for word in original_words
                        if word['start'] < end and (word['end'] > start
                           or word['start'] == word['end'] and word['start'] >= start)]
        if original_words and not window_words:
            continue
        words = caption_words(window_words)
        if remove_fillers:
            words = [word for word in words if not filler_word(word['word'])]
        if not words:
            # A segment with no usable word timing keeps its supplied cue.
            text = segment['text'].strip()
            append_cue(segment['start'], segment['end'], display_text(text) if remove_fillers else text)
            continue
        phrase = []
        for word in words:
            if word['start'] >= end or word['end'] <= start:
                continue
            candidate = phrase + [word]
            text = phrase_text(candidate)
            if phrase and (len(text.split()) > captions.words_per_line
                           or len(candidate) > max(6, captions.words_per_line) or len(text) > 32
                           or len(wrap_phrase(text).splitlines()) > captions.max_lines
                           or word['end'] - phrase[0]['start'] > 3
                           or word['start'] - phrase[-1]['end'] > .6):
                append_cue(phrase[0]['start'], phrase[-1]['end'], wrap_phrase(phrase_text(phrase)))
                phrase = []
            phrase.append(word)
        if phrase:
            append_cue(phrase[0]['start'], phrase[-1]['end'], wrap_phrase(phrase_text(phrase)))
    return cues
