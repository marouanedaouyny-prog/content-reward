"""Centralized source ranking for discovery.

The scorer turns observed public metadata into one comparable number. It never
invents evidence: a signal that was not observed stays unknown, the available
signals are renormalized, and the coverage of the evidence is reported next to
the score so a thin record cannot look like a strong one.
"""

import math
import re

from clipping.selection.scoring import score_signals

DEFAULT_WEIGHTS = {
    'velocity': 0.30,
    'relevance': 0.25,
    'engagement': 0.15,
    'freshness': 0.15,
    'channel_quality': 0.10,
    'transcript_signal': 0.05,
}

TRANSCRIPT_SIGNAL = {'AVAILABLE': 1.0, 'UNKNOWN': 0.5, 'UNAVAILABLE': 0.0}


def _tokens(value):
    if not isinstance(value, str):
        return set()
    return {word.casefold() for word in re.findall(r"[\w']+", value) if len(word) > 2}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


class SourceScorer:
    """Rank sources from observed public metadata."""

    def __init__(self, weights=None, freshness_window_days=14, minimum_age_hours=6.0,
                 velocity_reference=10000.0, view_reference=1000000.0):
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        if not math.isclose(sum(self.weights.values()), 1, abs_tol=1e-8):
            raise ValueError('Source-scoring weights must be normalized')
        self.freshness_window_days = max(1, int(freshness_window_days))
        self.minimum_age_hours = max(0.5, float(minimum_age_hours))
        self.velocity_reference = max(1.0, float(velocity_reference))
        self.view_reference = max(1.0, float(view_reference))

    def velocity(self, candidate):
        """Views per hour, damped for very young videos with a tiny sample size."""
        views = candidate.views
        age = candidate.age_hours
        if views is None or age is None:
            return None
        denominator = max(age, self.minimum_age_hours)
        rate = views / denominator
        confidence = age / (age + self.minimum_age_hours)
        return rate * confidence

    def relevance(self, candidate, keywords=None):
        terms = _tokens(keywords if isinstance(keywords, str) else ' '.join(keywords or []))
        if not terms:
            return None
        title = _tokens(candidate.title) | _tokens(candidate.description or '')
        if not title:
            return None
        return len(terms & title) / len(terms)

    def engagement(self, candidate):
        views = candidate.views
        likes = _number((candidate.metadata or {}).get('like_count'))
        comments = _number((candidate.metadata or {}).get('comment_count'))
        if not views or likes is None or comments is None:
            return None
        return min(1.0, max(0.0, (likes + comments) / views))

    def freshness(self, candidate):
        age = candidate.age_hours
        if age is None:
            return None
        window = self.freshness_window_days * 24
        return max(0.0, min(1.0, 1 - age / window))

    def signals(self, candidate, keywords=None):
        velocity = self.velocity(candidate)
        return {
            'velocity': {'value': (min(1.0, math.log1p(max(0.0, velocity)) / math.log1p(self.velocity_reference))
                                   if velocity is not None else None),
                         'basis': 'Lifetime views per hour, damped for very young uploads.'},
            'relevance': {'value': self.relevance(candidate, keywords),
                          'basis': 'Token overlap between the niche terms and the public title or description.'},
            'engagement': {'value': self.engagement(candidate),
                           'basis': 'Observed likes plus comments divided by views, capped at one.'},
            'freshness': {'value': self.freshness(candidate),
                          'basis': 'Age relative to the configured source freshness window.'},
            'channel_quality': {'value': _number((candidate.metadata or {}).get('channel_quality')),
                                'basis': 'Supplied channel-quality observation; unknown unless measured.'},
            'transcript_signal': {'value': TRANSCRIPT_SIGNAL.get(candidate.transcript_status),
                                  'basis': 'Transcript availability observed before acquisition. '
                                           'Unknown is not a rejection and carries a neutral signal.'},
        }

    def score(self, candidate, keywords=None):
        report = score_signals(self.signals(candidate, keywords), self.weights)
        report['note'] = ('Weighted available public evidence; missing signals are excluded and the '
                          'coverage is reported. The score ranks discovery candidates and is not a '
                          'prediction of future views.')
        return report

    def rank(self, candidates, keywords=None):
        scored = []
        for position, candidate in enumerate(candidates):
            report = self.score(candidate, keywords)
            scored.append((candidate, report, position))
        scored.sort(key=lambda item: (item[1]['score'] is None, -(item[1]['score'] or 0), item[2]))
        return [(candidate, report) for candidate, report, _ in scored]
