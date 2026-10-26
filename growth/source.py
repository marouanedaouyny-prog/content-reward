"""Cheap, transparent source filtering over metadata available before captions."""

import math
import re
from datetime import datetime, timezone

from clipping.selection.scoring import score_signals


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _keywords(values):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (tuple, list, set)):
        return set()
    return {word.casefold() for value in values if isinstance(value, str)
            for word in re.findall(r"[\w']+", value) if len(word) > 2}


class SourcePreFilter:
    """Rank public candidates before transcript or media acquisition.

    Unknown metadata is omitted and weights are renormalized. A source is only
    rejected when the observed signal coverage reaches the configured minimum.
    """

    def __init__(self, config):
        self.config = config
        self.weights = config.weights

    def score(self, source, *, keywords=None, now=None):
        source = source if isinstance(source, dict) else {}
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError('Source-filter reference time must include a timezone')
        views = _number(source.get('views', source.get('view_count')))
        age_hours = None
        try:
            published = datetime.fromisoformat(str(source['published_at']).replace('Z', '+00:00'))
            if published.tzinfo is not None:
                age_hours = (current - published).total_seconds() / 3600
                if age_hours < 0:
                    age_hours = None
        except (KeyError, TypeError, ValueError, OverflowError):
            pass

        velocity = _number(source.get('views_per_hour_since_upload'))
        if velocity is None and views is not None and age_hours:
            velocity = views / age_hours
        velocity_signal = (min(1.0, math.log1p(max(0, velocity)) / math.log1p(10000))
                           if velocity is not None else None)
        reach_signal = (min(1.0, math.log1p(max(0, views)) / math.log1p(1_000_000))
                        if views is not None else None)
        freshness = (max(0.0, min(1.0, 1 - age_hours / (self.config.freshness_window_days * 24)))
                     if age_hours is not None else None)

        terms = _keywords(keywords)
        title = _keywords(source.get('title', ''))
        relevance = (len(terms & title) / len(terms) if terms else None)

        engagement = _number(source.get('engagement_rate'))
        if engagement is None and views and views > 0:
            likes, comments = _number(source.get('likes')), _number(source.get('comments'))
            if likes is not None and comments is not None and likes >= 0 and comments >= 0:
                engagement = (likes + comments) / views
        engagement_signal = (min(1.0, max(0.0, engagement) / 0.05)
                             if engagement is not None and engagement >= 0 else None)

        duration = _number(source.get('duration'))
        min_seconds = self.config.min_duration_minutes * 60
        max_seconds = self.config.max_duration_hours * 3600
        duration_signal = (float(min_seconds <= duration <= max_seconds)
                           if duration is not None else None)
        signals = {
            'velocity': {'value': velocity_signal, 'basis': 'Lifetime views per hour from observed source count and age.'},
            'relevance': {'value': relevance, 'basis': 'Token overlap between configured niche terms and public title.'},
            'freshness': {'value': freshness, 'basis': 'Age relative to the configured source freshness window.'},
            'engagement': {'value': engagement_signal, 'basis': 'Observed likes plus comments divided by views, normalized to 5%.'},
            'channel_quality': self._provided(source.get('channel_quality'), 'Supplied channel-quality observation.'),
            'transcript_available': self._boolean(source.get('transcript_available'), 'Transcript availability observed before acquisition.'),
            'replay_available': self._boolean(source.get('replay_available'), 'Replay-signal availability observed before acquisition.'),
            'total_views': {'value': reach_signal, 'basis': 'Log-normalized public source view count.'},
            'duration': {'value': duration_signal, 'basis': 'Observed source duration within configured long-form bounds.'},
        }
        report = score_signals(signals, self.weights)
        if report['evidence_coverage'] == 0:
            report['score'] = None
        return {**report, 'weights': self.weights,
                'missing_signals': report['missing_signals'],
                'note': 'Metadata pre-filter only; score is not a virality or clip-performance prediction.'}

    def accepts(self, report):
        if not self.config.enabled:
            return {'accepted': True, 'basis': 'filter_disabled'}
        if report.get('evidence_coverage', 0) < self.config.minimum_coverage:
            return {'accepted': True, 'basis': 'insufficient_evidence'}
        if report.get('score') is None:
            return {'accepted': True, 'basis': 'insufficient_evidence'}
        accepted = report['score'] >= self.config.minimum_score
        return {'accepted': accepted,
                'basis': 'metadata_score_passed' if accepted else 'metadata_score_below_threshold'}

    def rank(self, sources, *, keywords=None, now=None):
        ranked = []
        for position, source in enumerate(sources):
            report = self.score(source, keywords=keywords, now=now)
            decision = self.accepts(report)
            if not decision['accepted']:
                continue
            ranked.append(({**source, 'source_prefilter': {**report, 'decision': decision}},
                           report['score'], position))
        ranked.sort(key=lambda item: (item[1] is None, -(item[1] or 0), item[2]))
        return [source for source, _, _ in ranked]

    @staticmethod
    def _provided(value, basis):
        number = _number(value)
        if number is None or not 0 <= number <= 1:
            return {'value': None, 'basis': basis + ' Value unavailable or invalid.'}
        return {'value': number, 'basis': basis}

    @staticmethod
    def _boolean(value, basis):
        return {'value': float(value) if isinstance(value, bool) else None, 'basis': basis}
