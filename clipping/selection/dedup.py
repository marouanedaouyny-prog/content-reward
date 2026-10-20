"""Duplicate evidence: source overlap, text, quotes and optional real embeddings."""

import math
import re
import unicodedata
from collections import Counter

from app.core.config import load_settings


def words(text):
    normalized = unicodedata.normalize('NFKC', str(text or '')).casefold().replace('’', "'")
    return re.findall(r"\w+(?:'\w+)*", normalized, re.UNICODE)


def _grams(tokens, size):
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def _overlap(first, second):
    if not first.get('source_id') or first.get('source_id') != second.get('source_id'):
        return 0.0
    try:
        a, b = first['clip_plan'], second['clip_plan']
        start, duration = a['start_seconds'], a['duration_seconds']
        other, length = b['start_seconds'], b['duration_seconds']
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in (start, duration, other, length)) or min(start, other) < 0 or min(duration, length) <= 0:
            raise ValueError
        return max(0, min(start + duration, other + length) - max(start, other)) / min(duration, length)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('Duplicate comparison needs valid source intervals') from error


def _semantic(first, second):
    model = first.get('embedding_model')
    if not isinstance(model, str) or not model or model != second.get('embedding_model'):
        return None
    a, b = first.get('embedding'), second.get('embedding')
    if not isinstance(a, list) or not isinstance(b, list) or not a or len(a) != len(b) or len(a) > 8192:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in [*a, *b]):
        return None
    # Scaling before the norm prevents overflow from finite but enormous values.
    scale_a, scale_b = max(map(abs, a)), max(map(abs, b))
    if not scale_a or not scale_b:
        return None
    a, b = [v / scale_a for v in a], [v / scale_b for v in b]
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) /
                        (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))))


def compare_moments(first, second, *, settings=None):
    config = (settings or load_settings()).dedup
    a, b = words(first.get('source_excerpt')), words(second.get('source_excerpt'))
    counts_a, counts_b = Counter(a), Counter(b)
    denominator = min(len(a), len(b))
    text_similarity = sum((counts_a & counts_b).values()) / denominator if denominator else 0.0
    # Require shared sequences as well as vocabulary; word order changes meaning.
    grams_a, grams_b = _grams(a, 3), _grams(b, 3)
    sequence_similarity = len(grams_a & grams_b) / min(len(grams_a), len(grams_b)) if grams_a and grams_b else 0.0
    transcript_similarity = min(text_similarity, sequence_similarity)
    quote = bool(_grams(a, config.quote_words) & _grams(b, config.quote_words))
    overlap, semantic = _overlap(first, second), _semantic(first, second)
    reasons = []
    if overlap >= config.timestamp_overlap_threshold:
        reasons.append('timestamp_overlap')
    if denominator >= 4 and transcript_similarity >= config.transcript_similarity_threshold:
        reasons.append('transcript_similarity')
    if quote:
        reasons.append('repeated_quote')
    if semantic is not None and semantic >= config.semantic_similarity_threshold:
        reasons.append('semantic_similarity')
    return {'duplicate': bool(reasons), 'reasons': reasons, 'timestamp_overlap': overlap,
            'transcript_similarity': transcript_similarity, 'repeated_quote': quote,
            'semantic_similarity': semantic}
