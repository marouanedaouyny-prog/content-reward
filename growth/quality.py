"""Composite production quality score from mechanical QC and growth reports."""

from app.core.config import load_settings
from clipping.selection.scoring import score_signals

# PRD-GROWTH section 44 weights; validated to normalize on every call.
WEIGHTS = {'video_quality': 0.15, 'audio_quality': 0.15, 'subtitle_quality': 0.15,
           'hook_score': 0.20, 'retention_score': 0.20, 'completeness': 0.15}

# Mechanical export checks grouped into the three media component scores.
MEDIA_GROUPS = {
    'video_quality': ('file_size', 'full_decode', 'video', 'resolution', 'duration',
                      'fps', 'no_black_frames'),
    'audio_quality': ('audio', 'audible_audio', 'no_excessive_silence'),
    'subtitle_quality': ('captions', 'subtitle_bounds'),
}


def completeness(quality):
    """PRD-GROWTH section 48: understandable start, one complete idea, real payoff."""
    if not isinstance(quality, dict) or 'completed_ending' not in quality:
        return None
    value = 0.0
    if quality.get('completed_ending') and not quality.get('ending_question'):
        value += 0.5
    if not quality.get('context_dependent_opening') and not quality.get('mid_sentence_opening'):
        value += 0.3
    if not quality.get('promotional') and not quality.get('host_meta_setup'):
        value += 0.2
    return round(value, 2)


def score_quality(*, growth=None, checks=None, settings=None):
    """Weighted composite of mechanical export checks and growth report components.

    `checks` is the post-render media QC mapping; `growth` is the planner's
    growth report for the selected moment. Missing components are excluded,
    coverage is reported, and `passed` stays None until every component exists.
    """
    settings = settings or load_settings()
    growth = growth if isinstance(growth, dict) else {}
    components = {}
    if isinstance(checks, dict):
        for group, keys in MEDIA_GROUPS.items():
            present = [key for key in keys if key in checks]
            if present:
                components[group] = {'value': sum(bool(checks[key]) for key in present) / len(present),
                                     'basis': 'Mechanical post-render export checks: ' + ', '.join(present)}
    hook = growth.get('hook')
    if isinstance(hook, dict) and isinstance(hook.get('value'), (int, float)):
        components['hook_score'] = {'value': hook['value'], 'basis': hook.get('basis')}
    retention = growth.get('retention')
    if isinstance(retention, dict) and isinstance(retention.get('value'), (int, float)):
        components['retention_score'] = {'value': retention['value'], 'basis': retention.get('basis')}
    if isinstance(growth.get('completeness'), (int, float)):
        components['completeness'] = {'value': growth['completeness'],
                                      'basis': 'Planner transcript flags for complete-idea structure'}
    report = score_signals(components, WEIGHTS)
    minimum = settings.quality.minimum_score
    complete = not report['missing_signals']
    report.update(minimum_score=minimum, passed=(report['score'] >= minimum) if complete else None,
                  evaluation='complete' if complete else 'incomplete_coverage')
    return report
