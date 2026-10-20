"""Small, explainable adjustments based on independent observed clips."""

from statistics import mean

from analytics.collectors import latest_performance
from app.core.config import load_settings


def feedback_adjustment(store, *, caption_style, duration_seconds=None, opening_question=None, settings=None):
    settings = settings or load_settings()
    clips = {clip['id']: clip for clip in store.list_clips()}
    by_clip = {}
    for observation in latest_performance(store):
        clip = clips.get(observation.clip_id)
        if clip and duration_seconds is not None:
            duration = clip['settings'].get('source_clip_plan', {}).get('duration_seconds')
            if duration is None or int(duration // 10) != int(duration_seconds // 10):
                continue
        if clip and opening_question is not None:
            if clip['settings'].get('transcript_features', {}).get('opening_question') is not opening_question:
                continue
        if clip and clip['caption_style'] == caption_style and observation.completion_rate is not None:
            by_clip.setdefault(observation.clip_id, []).append(observation.completion_rate)
    values = [mean(items) for items in by_clip.values()]
    supported = len(values) >= settings.feedback.minimum_samples
    adjustment = ((mean(values) - .5) * settings.feedback.maximum_adjustment * 2) if supported else 0
    adjustment = max(-settings.feedback.maximum_adjustment, min(settings.feedback.maximum_adjustment, adjustment))
    return dict(adjustment=round(adjustment, 6), samples=len(values),
                average_completion_rate=mean(values) if values else None,
                basis='Latest observed completion per independent clip, averaged across platforms; '
                      'bounded comparison to 50% completion. Correlation is not causation.',
                minimum_samples=settings.feedback.minimum_samples, supported=supported)


def adjust_candidate(candidate, feedback):
    original = candidate.get('selection', {}).get('score', 0)
    adjusted = max(0, min(1, original + feedback['adjustment']))
    return {**candidate, 'feedback': {**feedback, 'original_score': original, 'adjusted_score': adjusted}}


def feedback_for_order(controller):
    cache = {}
    with controller.store.connection() as db:
        has_history = db.execute('SELECT 1 FROM performance_metrics LIMIT 1').fetchone() is not None

    def evaluate(candidate):
        if not has_history:
            return dict(adjustment=0, samples=0, supported=False,
                        basis='No measured historical performance; base selection score is unchanged.')
        duration = candidate['clip_plan']['duration_seconds']
        question = candidate.get('transcript_features', {}).get('opening_question')
        key = (int(duration // 10), question)
        if key not in cache:
            cache[key] = feedback_adjustment(controller.store, caption_style=controller.config.caption_style,
                duration_seconds=duration, opening_question=question)
        return cache[key]
    return evaluate
