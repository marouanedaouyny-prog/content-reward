"""Deterministic ranking with explicit evidence and no invented model outputs."""

import math
from datetime import datetime, timezone


def score_signals(signals, weights):
    if (not weights or any(isinstance(w, bool) or not isinstance(w, (int, float))
                          or not math.isfinite(w) or w < 0 for w in weights.values())
            or not math.isclose(sum(weights.values()), 1, abs_tol=1e-8)):
        raise ValueError('Selection weights must be finite, nonnegative and normalized')
    report, missing, total, coverage = {}, [], 0.0, 0.0
    for name, weight in weights.items():
        item = signals.get(name)
        value = item.get('value') if isinstance(item, dict) else item
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError('Selection signals must be finite values between zero and one')
        contribution = weight * value if value is not None else None
        report[name] = {'value': value, 'weight': weight, 'weighted_contribution': contribution,
                        'basis': item.get('basis') if isinstance(item, dict) else 'Supplied normalized observation'}
        if value is None:
            missing.append(name)
        else:
            total += contribution
            coverage += weight
    return {'score': total / coverage if coverage else 0.0, 'signals': report,
            'evidence_coverage': coverage, 'missing_signals': missing,
            'note': 'Weighted available evidence; missing signals are excluded and coverage is reported. '
                    'An editorial ranking score is not a probability of future views.'}


def _nonnegative(value):
    return (float(value) if not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0 else None)


def source_signals(source, *, now=None):
    views = _nonnegative(source.get('view_count', source.get('views')))
    likes, comments = (_nonnegative(source.get(key)) for key in ('like_count', 'comment_count'))
    published = source.get('published_at')
    age = None
    try:
        date = datetime.fromisoformat(published.replace('Z', '+00:00'))
        current = now or datetime.now(timezone.utc)
        if date.tzinfo is not None:
            seconds = (current - date).total_seconds()
            age = seconds / 3600 if seconds > 0 else None
    except (AttributeError, TypeError, ValueError):
        pass
    return {'source_views': views,
            'views_per_hour': views / age if views is not None and age else None,
            'engagement_rate': (likes + comments) / views if views and likes is not None and comments is not None else None,
            'velocity_basis': 'Lifetime views / known source age; not a measured recent growth rate'}


def score_candidate(candidate, selection, *, source=None):
    quality = candidate['quality']
    editorial = selection.editorial
    features = candidate['transcript_features']
    hook = editorial['baseline']
    if quality['filler_opening']:
        hook -= editorial['filler_penalty']
    elif features['opening_question']:
        hook += editorial['question_bonus']
    if features['opening_topic_matches']:
        hook += min(editorial['opening_topic_cap'], features['opening_topic_matches'] * editorial['opening_topic_bonus'])
    if quality['context_dependent_opening'] or quality['mid_sentence_opening']:
        hook -= editorial['referential_penalty']
    observed = source_signals(source or {})
    signals = {
        'hook': {'value': max(0, min(1, hook / 100)),
                 'basis': 'Configured transcript opening features / 100; not a measured audience response'},
        'semantic': {'value': max(0, min(1, candidate['editorial_score'] / 100)),
                     'basis': 'Configured topic, concrete-detail, duration and speech-gap heuristics / 100; no language model'},
        'completeness': {'value': float(quality['completed_ending'] and not features['ending_question']),
                         'basis': 'Source sentence punctuation and question/answer ending'},
        'standalone': {'value': float(not any(quality[key] for key in (
            'filler_opening', 'context_dependent_opening', 'mid_sentence_opening',
            'intro_or_outro', 'host_meta_setup', 'promotional'))),
            'basis': 'Observable transcript context, introduction and promotion flags'},
    }
    if 'replay_score' in candidate:
        signals['replay'] = {'value': candidate['replay_score'],
                             'basis': 'Duration-weighted observed YouTube replay intensity in this window'}
    if observed['engagement_rate'] is not None:
        signals['engagement'] = {'value': min(1.0, observed['engagement_rate']),
                                 'basis': 'Observed (likes + comments) / views, capped at one'}
    # Velocity has no cohort normalization; emotion/energy have no measured audio
    # in caption-first discovery. Keep these unknown rather than simulating AI.
    report = score_signals(signals, selection.weights)
    report['source_observations'] = observed
    return report
