"""Progressive eligibility for discovered sources.

One strict filter set turns a rich candidate pool into zero matches. The
eligibility engine therefore evaluates three tiers in order and keeps relaxing
until it has enough sources or runs out of tiers. Every rejection is counted
with a reason so a zero-result run can explain itself.

An unknown transcript status is never a rejection. Missing metadata is a
penalty or an unknown state, never a crash.
"""

import math
from dataclasses import dataclass

TIERS = ('strict', 'medium', 'relaxed')


@dataclass(frozen=True)
class EligibilityTier:
    """One relaxation level of the source rules."""

    name: str
    min_duration_minutes: int
    min_views: int
    max_age_days: int
    min_score: float
    require_views: bool = True
    require_age: bool = True

    def as_dict(self):
        return {'name': self.name, 'min_duration_minutes': self.min_duration_minutes,
                'min_views': self.min_views, 'max_age_days': self.max_age_days,
                'min_score': self.min_score, 'require_views': self.require_views,
                'require_age': self.require_age}


DEFAULT_TIERS = {
    'strict': EligibilityTier('strict', 45, 100000, 7, 0.70, require_views=True, require_age=True),
    'medium': EligibilityTier('medium', 30, 25000, 30, 0.55, require_views=True, require_age=False),
    'relaxed': EligibilityTier('relaxed', 20, 5000, 90, 0.45, require_views=False, require_age=False),
}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


class EligibilityEngine:
    """Evaluate candidates against the tier rules and explain every rejection."""

    def __init__(self, tiers=None, whitelist_boost=0.0, blacklist=None):
        self.tiers = {name: tier for name, tier in (tiers or DEFAULT_TIERS).items()}
        self.whitelist_boost = max(0.0, min(0.5, float(whitelist_boost)))
        self.blacklist = set(blacklist or ())

    def _boosted(self, score, whitelisted):
        if not whitelisted or score is None:
            return score
        return min(1.0, score + self.whitelist_boost)

    def evaluate(self, candidate, tier, score, *, whitelisted=False):
        """Return (accepted, reason). The reason is a stable machine-readable code."""
        if candidate.id in self.blacklist:
            return False, 'blacklisted'
        if candidate.is_live:
            return False, 'live'
        duration = candidate.duration_seconds
        if duration is None:
            return False, 'duration_unknown'
        if duration < tier.min_duration_minutes * 60:
            return False, 'duration'
        if duration > 6 * 3600:
            return False, 'duration'
        if tier.require_views:
            if candidate.views is None:
                return False, 'views_unknown'
            if candidate.views < tier.min_views:
                return False, 'views'
        elif candidate.views is not None and candidate.views < max(0, tier.min_views // 4):
            return False, 'views'
        age = candidate.age_hours
        if tier.require_age:
            if age is None:
                return False, 'age_unknown'
            if age / 24 > tier.max_age_days:
                return False, 'age'
        elif age is not None and age / 24 > tier.max_age_days * 2:
            return False, 'age'
        value = self._boosted(score, whitelisted)
        if value is None:
            return False, 'score'
        if value < tier.min_score:
            return False, 'score'
        return True, None

    def select(self, candidates, scores, *, target=5, minimum=2, whitelisted=()):
        """Select the best sources, relaxing tiers until enough candidates exist.

        `scores` maps a candidate identifier to its numeric source score. The
        tiers are evaluated in order and the first tier that produces enough
        candidates wins, so a run that needed the relaxed tier says so.
        Returns a dict with the selected candidates, the tier that produced
        them, the per-tier counts and the rejection reasons.
        """
        whitelist = set(whitelisted or ())
        target = max(1, int(target))
        report = {'tier': None, 'selected': [], 'counts': {}, 'rejected': {},
                  'shortfall': 0, 'meets_minimum': False}
        best = ([], None)
        for name in TIERS:
            tier = self.tiers.get(name)
            if tier is None:
                continue
            accepted = []
            for candidate in candidates:
                ok, reason = self.evaluate(candidate, tier, scores.get(candidate.id),
                                           whitelisted=candidate.id in whitelist)
                if ok:
                    accepted.append(candidate)
                else:
                    report['rejected'][reason] = report['rejected'].get(reason, 0) + 1
            report['counts'][name] = len(accepted)
            if accepted and not best[0]:
                best = (accepted, name)
            if len(accepted) >= target:
                report['tier'] = name
                report['selected'] = accepted[:target]
                report['shortfall'] = 0
                report['meets_minimum'] = len(report['selected']) >= max(1, int(minimum))
                return report
        if best[0]:
            report['tier'] = best[1]
            report['selected'] = best[0][:target]
        report['shortfall'] = max(0, int(minimum) - len(report['selected']))
        report['meets_minimum'] = len(report['selected']) >= max(1, int(minimum))
        return report
