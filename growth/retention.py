"""Retention signals and penalties from transcript timing; not an audience forecast."""

import re

from growth.hook import WEAK_PHRASES, normalized_text, opening_text

# PRD-GROWTH section 8 signal families, reported in a stable order.
SIGNAL_ORDER = ('strong_first_sentence', 'low_silence', 'fast_information_density',
                'sentence_continuity', 'clear_payoff', 'clip_length', 'topic_continuity')

# Discourse resets that suggest the clip contains more than one topic.
TRANSITIONS = re.compile(
    r'\b(?:anyway|moving on|next up|switching gears|but anyway|another thing)\b', re.IGNORECASE)

# Roughly conversational upper bound; speech above this stays capped at one.
DENSE_WORDS_PER_SECOND = 2.8

RETENTION_BASIS = ('Heuristic transcript timing, structure and length signals with explicit '
                   'penalties; not a measured retention curve or viewer forecast.')


def _finite(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and value == value and value not in (float('inf'), float('-inf')))


def _sentences(text):
    return re.findall(r'''[^.!?。！？]+[.!?。！？]+''', text)


def _repeated_sentence(text):
    seen = set()
    for sentence in _sentences(text):
        words = tuple(re.findall(r"[a-z']+", sentence.lower()))
        if len(words) >= 4 and words in seen:
            return True
        seen.add(words)
    return False


def _length_fit(duration):
    if 24 <= duration <= 42:
        return 1.0
    if 18 <= duration <= 60:
        return 0.75
    return 0.4


class RetentionScorer:
    """Score retention potential from observable transcript evidence only."""

    def score(self, candidate):
        quality = candidate.get('quality') or {}
        features = candidate.get('transcript_features') or {}
        plan = candidate.get('clip_plan') or {}
        text = normalized_text(candidate.get('source_excerpt'))
        signals, penalties = {}, {}
        if text:
            opening = opening_text(candidate.get('source_excerpt'))
            if quality.get('mid_sentence_opening') or quality.get('context_dependent_opening'):
                signals['strong_first_sentence'] = 0.2
            elif quality.get('filler_opening') or WEAK_PHRASES.match(opening):
                signals['strong_first_sentence'] = 0.4
            elif features.get('opening_question') or re.search(r'\d', opening):
                signals['strong_first_sentence'] = 1.0
            else:
                signals['strong_first_sentence'] = 0.7
        ratio = quality.get('speech_ratio')
        if _finite(ratio):
            signals['low_silence'] = max(0.0, min(1.0, ratio))
        words_per_second = features.get('words_per_second')
        if _finite(words_per_second):
            signals['fast_information_density'] = max(0.0, min(1.0, words_per_second / DENSE_WORDS_PER_SECOND))
        if 'mid_sentence_opening' in quality or 'context_dependent_opening' in quality:
            signals['sentence_continuity'] = float(not (quality.get('mid_sentence_opening')
                                                        or quality.get('context_dependent_opening')))
        if 'completed_ending' in quality:
            signals['clear_payoff'] = float(bool(quality.get('completed_ending'))
                                            and not bool(quality.get('ending_question')))
        duration = plan.get('duration_seconds')
        if _finite(duration) and duration > 0:
            signals['clip_length'] = _length_fit(duration)
        if text:
            signals['topic_continuity'] = 1.0 / (1.0 + len(TRANSITIONS.findall(text)))
        # PRD-GROWTH section 8 penalties; each is skipped without its evidence.
        if quality.get('filler_opening'):
            penalties['slow_intro'] = 0.06
        gap = quality.get('largest_speech_gap')
        if _finite(gap) and gap >= 2.0:
            penalties['long_pauses'] = 0.08
        if text and _repeated_sentence(text):
            penalties['repetition'] = 0.10
        if quality.get('host_meta_setup') or quality.get('context_dependent_opening'):
            penalties['unnecessary_setup'] = 0.06
        silence = quality.get('silence_seconds')
        if _finite(silence) and silence >= 1.5:
            penalties['dead_air'] = 0.06
        if quality.get('ending_question'):
            penalties['weak_ending'] = 0.08
        if quality.get('mid_sentence_opening'):
            penalties['mid_sentence_start'] = 0.10
        if 'completed_ending' in quality and not quality.get('completed_ending'):
            penalties['mid_answer_ending'] = 0.08
        values = [value for value in signals.values() if value is not None]
        if not values:
            return {'value': None, 'signals': signals, 'penalties': penalties,
                    'missing_signals': list(SIGNAL_ORDER),
                    'basis': 'No transcript timing or structure evidence was supplied; retention not evaluated.'}
        value = max(0.0, round(sum(values) / len(values) - sum(penalties.values()), 4))
        return {'value': value, 'signals': signals, 'penalties': penalties,
                'missing_signals': [name for name in SIGNAL_ORDER if name not in signals],
                'basis': RETENTION_BASIS}
