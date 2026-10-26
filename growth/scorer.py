"""Centralized growth score from configured weights and observed evidence."""

import re

from app.core.config import load_settings
from clipping.selection.scoring import score_signals
from growth.hook import HookScorer, normalized_text
from growth.quality import completeness
from growth.retention import RetentionScorer

SHARE_MARKERS = re.compile(
    r"\$\s?\d|\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?\s?(?:percent|%|million|billion|x)\b"
    r"|\b(?:millionaire|bankrupt|mistake|secret|risk|warning|proof)\b", re.IGNORECASE)
EMOTION_MARKERS = re.compile(
    r"\b(?:love|hate|afraid|scared|angry|furious|excited|shocked|proud|embarrassed|regret"
    r"|screaming|crying|amazing|terrible|worst|best)\b", re.IGNORECASE)
NOVELTY_MARKERS = re.compile(
    r"\b(?:nobody|no one|never (?:been|told|seen|heard)|first time|didn'?t (?:expect|see)"
    r"|unexpected|unheard of|surprising|surprise)\b", re.IGNORECASE)
LESSON_MARKERS = re.compile(
    r"\b(?:lesson|takeaway|remember|rule|principle|advice|the key is|what i learned"
    r"|why most people|most people)\b", re.IGNORECASE)

NO_TEXT = 'No transcript text was supplied; this growth signal was not evaluated.'


def _finite(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and value == value and value not in (float('inf'), float('-inf')))


class GrowthScorer:
    """PRD-GROWTH section 4 weighted growth score over available evidence."""

    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.weights = self.settings.growth_scoring.model_dump()

    def score(self, candidate, *, keywords=None, source=None):
        hook = HookScorer().score(candidate)
        retention = RetentionScorer().score(candidate)
        quality = candidate.get('quality') or {}
        features = candidate.get('transcript_features') or {}
        text = normalized_text(candidate.get('source_excerpt'))
        signals = {
            'hook_strength': {'value': hook.get('value'), 'basis': hook.get('basis')},
            'retention_potential': {'value': retention.get('value'), 'basis': retention.get('basis')},
            'shareability': self._markers(text, SHARE_MARKERS,
                'Money, number and stakes markers in the supplied transcript; not a measured share rate.'),
            'standalone_clarity': self._standalone(quality),
            'emotional_intensity': self._markers(text, EMOTION_MARKERS,
                'Emotion-word markers in the supplied transcript; audio energy was not measured.'),
            'novelty': self._markers(text, NOVELTY_MARKERS,
                'Unexpectedness markers in the supplied transcript; novelty is not independently verified.'),
            'niche_relevance': self._niche(features, keywords),
            'follow_potential': self._follow(quality, text),
        }
        report = score_signals(signals, self.weights)
        report.update(hook=hook, retention=retention, completeness=completeness(quality),
                      weights=self.weights)
        return report

    def rank(self, candidates, *, keywords=None, source=None):
        """Order candidates by growth score; ordering is editorial, not predictive."""
        scored = [(self.score(candidate, keywords=keywords, source=source), candidate)
                  for candidate in candidates]
        scored.sort(key=lambda item: (-item[0]['score'],
                                      item[1].get('clip_plan', {}).get('start_seconds') or 0))
        return [candidate for _, candidate in scored]

    @staticmethod
    def _markers(text, pattern, basis):
        if not text:
            return {'value': None, 'basis': NO_TEXT}
        return {'value': min(1.0, len(pattern.findall(text)) / 3), 'basis': basis}

    @staticmethod
    def _standalone(quality):
        blockers = ('context_dependent_opening', 'mid_sentence_opening',
                    'intro_or_outro', 'promotional', 'host_meta_setup')
        if any(quality.get(key) is True for key in blockers):
            value = 0.0
        elif not all(isinstance(quality.get(key), bool) for key in (*blockers, 'filler_opening')):
            return {'value': None, 'basis': 'Standalone transcript flags are incomplete; clarity not evaluated.'}
        elif quality.get('filler_opening'):
            value = 0.5
        else:
            value = 1.0
        return {'value': value,
                'basis': 'Observed opening, context and promotion flags in the supplied transcript.'}

    @staticmethod
    def _niche(features, keywords):
        if not keywords:
            return {'value': None, 'basis': 'No niche keywords were supplied; niche relevance not evaluated.'}
        matches = features.get('topic_matches')
        if not _finite(matches):
            return {'value': None, 'basis': 'Topic keyword matches were not recorded for this candidate.'}
        return {'value': min(1.0, max(0.0, matches) / 2),
                'basis': 'Configured topic keyword matches recorded by the planner; not measured audience interest.'}

    @staticmethod
    def _follow(quality, text):
        if 'completed_ending' not in quality:
            return {'value': None, 'basis': 'No transcript flags were supplied; follow potential not evaluated.'}
        if not quality.get('completed_ending'):
            value = 0.2
        else:
            value = 0.5 + (0.5 if text and LESSON_MARKERS.search(text) else 0.0)
        return {'value': value,
                'basis': 'Complete-idea structure and lesson markers; not measured follower conversion.'}
