"""Opening-second hook analysis from supplied transcript text; no invented claims."""

import re

# Non-speech caption markers are display furniture, not spoken words.
NON_SPEECH = re.compile(
    r'\[(?:music|applause|laughter|laughs?|laughing|cheering|cheers|inaudible|silence|crosstalk)\]',
    re.IGNORECASE)

# PRD-GROWTH section 5: weak opening phrases that delay the point of a clip.
WEAK_PHRASES = re.compile(
    r"^(?:so\s+)?basically\b"
    r"|^today\s+we(?:'re|\s+are)\s+(?:going|covering)\b"
    r"|^let\s+me\s+(?:explain|start|begin)\b"
    r"|^as\s+i\s+was\s+saying\b"
    r"|^in\s+this\s+(?:video|episode|podcast|clip)\b"
    r"|^for\s+those\s+who\s+(?:don'?t\s+know|missed)\b"
    r"|^welcome\s+back\b",
    re.IGNORECASE)

# Marker families evaluated on the clip opening. Patterns describe wording;
# a match never asserts that the moment will perform well.
MARKERS = {
    'surprise': r"\b(?:unbelievable|shocking|insane|out of nowhere|you won'?t believe|wait (?:until|till))\b",
    'curiosity': (r"\b(?:nobody (?:tells|knew|warned)|the secret|didn'?t (?:expect|know|see coming)"
                  r"|here'?s (?:why|how|what)|what happens (?:next|when)|the reason)\b"),
    'conflict': r"\b(?:scam|lied|lies|fake|backlash|hated|ruined|cheated|exposed|worst (?:take|advice))\b",
    'bold_statement': r"\b(?:never|biggest|only|impossible|guaranteed|millions|bankrupt|always fails)\b",
    'clear_promise': r"\b(?:how to|the way to|you (?:need|have) to|only way|steps to|the formula)\b",
    'unexpected_fact': r"\b(?:did you know|turns out|in fact|the truth is|actually)\b",
    'emotional_line': r"\b(?:terrified|furious|devastated|heartbroken|excited|angry|crying|amazing|disgusting)\b",
    'authority_statement': (r"\b(?:i (?:built|made|ran|lost|earned|learned)"
                            r"|we (?:made|built|generated|learned)|let me be clear|i'?ll tell you)\b"),
}
# PRD-GROWTH section 5 label priority; strong questions come from planner features.
PRIORITY = ('surprise', 'curiosity', 'conflict', 'bold_statement', 'strong_question',
            'clear_promise', 'unexpected_fact', 'emotional_line', 'authority_statement')

HOOK_BASIS = ('Rule-based hook markers detected in the supplied opening text; labels describe '
              'the wording and are not verified audience reactions or fabricated claims.')


def normalized_text(text):
    """Collapse caption furniture and whitespace for marker matching only."""
    return ' '.join(NON_SPEECH.sub(' ', str(text or '').replace('>>', ' ')).split())


def opening_text(text):
    """The first spoken sentence (bounded), used as the hook under evaluation."""
    text = normalized_text(text)
    end = re.search(r'''[.!?。！？]["'”’»」』）)\]}]*''', text)
    if end and end.end() <= 240:
        return text[:end.end()]
    return text[:240]


class HookScorer:
    """Score opening-second hook strength from observable transcript evidence."""

    def score(self, candidate):
        quality = candidate.get('quality') or {}
        features = candidate.get('transcript_features') or {}
        opening = opening_text(candidate.get('source_excerpt'))
        if not opening:
            return {'value': None, 'hook_type': None, 'matched': [], 'opening_quality': None,
                    'weak_opening': None, 'opening': '',
                    'basis': 'No opening text or transcript flags were supplied; hook strength not evaluated.'}
        if quality.get('mid_sentence_opening') or quality.get('context_dependent_opening'):
            opening_quality = 0.2
        elif WEAK_PHRASES.match(opening) or quality.get('filler_opening'):
            opening_quality = 0.3
        elif quality.get('intro_or_outro'):
            opening_quality = 0.4
        else:
            opening_quality = 1.0
        found = {name for name, pattern in MARKERS.items() if re.search(pattern, opening, re.IGNORECASE)}
        if features.get('opening_question'):
            found.add('strong_question')
        matched = [name for name in PRIORITY if name in found]
        evidence = min(1.0, 0.35 * len(matched))
        value = round(opening_quality * (0.5 + 0.5 * evidence), 4)
        return {'value': value, 'hook_type': matched[0] if matched else 'neutral', 'matched': matched,
                'opening_quality': opening_quality, 'weak_opening': opening_quality < 1.0,
                'opening': opening[:160], 'basis': HOOK_BASIS}
