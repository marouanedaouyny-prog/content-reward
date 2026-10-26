"""Account-based local posting recommendations and spacing checks."""

from collections import defaultdict
from datetime import datetime, time, timedelta
from statistics import mean
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _aware(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Posting times must include a timezone')
    return parsed


def _parse_windows(windows):
    result = []
    for value in windows:
        try:
            start, end = value.split('-', 1)
            start_time = time.fromisoformat(start)
            end_time = time.fromisoformat(end)
        except (AttributeError, ValueError) as error:
            raise ValueError('Posting windows must use HH:MM-HH:MM') from error
        if start_time >= end_time:
            raise ValueError('Posting windows must start before they end on the same day')
        result.append((start_time, end_time))
    if not result:
        raise ValueError('At least one cold-start posting window is required')
    return sorted(result)


class PostingTimeOptimizer:
    """Recommend measured weekday/hour slots, otherwise configured fallback windows."""

    def __init__(self, minimum_samples=5):
        if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
            raise ValueError('minimum_samples must be a positive integer')
        self.minimum_samples = minimum_samples

    def recommend(self, platform, history, *, timezone_name, default_windows, now=None):
        try:
            zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, TypeError) as error:
            raise ValueError('Unknown posting timezone') from error
        windows = _parse_windows(default_windows)
        current = _aware(now or datetime.now(zone)).astimezone(zone)
        groups = defaultdict(list)
        for item in history:
            if not isinstance(item, dict) or item.get('platform') != platform:
                continue
            try:
                posted = _aware(item['posted_at']).astimezone(zone)
                if posted > current:
                    continue
                views = item.get('views')
                followers = item.get('followers_gained')
                if (isinstance(views, bool) or not isinstance(views, int) or views <= 0
                        or isinstance(followers, bool) or not isinstance(followers, int) or followers < 0):
                    continue
                groups[(posted.weekday(), posted.hour)].append(followers / views * 1000)
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        measured = [(key, values) for key, values in groups.items() if len(values) >= self.minimum_samples]
        if measured:
            (weekday, hour), values = max(measured, key=lambda item: (mean(item[1]), len(item[1])))
            recommended = self._next_weekday_hour(current, weekday, hour)
            return {'recommended_at': recommended, 'timezone': timezone_name,
                    'basis': 'account_history', 'samples': len(values),
                    'followers_per_1000_views': round(mean(values), 4)}

        recommended = self._next_window(current, windows)
        return {'recommended_at': recommended, 'timezone': timezone_name,
                'basis': 'configured_fallback', 'samples': 0,
                'followers_per_1000_views': None}

    @staticmethod
    def _next_weekday_hour(current, weekday, hour):
        for offset in range(8):
            day = current.date() + timedelta(days=offset)
            if day.weekday() != weekday:
                continue
            candidate = datetime.combine(day, time(hour), current.tzinfo)
            if candidate > current:
                return candidate
        raise ValueError('Could not find a future account-history slot')

    @staticmethod
    def _next_window(current, windows):
        for offset in range(8):
            day = current.date() + timedelta(days=offset)
            for start, _ in windows:
                candidate = datetime.combine(day, start, current.tzinfo)
                if candidate > current:
                    return candidate
        raise ValueError('Could not find a future configured posting window')


def content_spacing_violations(candidate, existing, *, max_posts_per_day=3,
                               minimum_gap_minutes=180, same_source_hours=8,
                               same_topic_hours=6, timezone_name='UTC'):
    """Return policy codes that would make a prepared queue entry too crowded."""
    zone = ZoneInfo(timezone_name)
    target = _aware(candidate['scheduled_at']).astimezone(zone)
    parsed = [(_aware(item['scheduled_at']).astimezone(zone), item) for item in existing]
    violations = set()
    same_day = [stamp for stamp, _ in parsed if stamp.date() == target.date()]
    if len(same_day) + 1 > max_posts_per_day:
        violations.add('max_posts_per_day')
    for stamp, item in parsed:
        gap_minutes = abs((target - stamp).total_seconds()) / 60
        gap_hours = gap_minutes / 60
        if gap_minutes < minimum_gap_minutes:
            violations.add('minimum_gap')
        if (candidate.get('source_id') and candidate.get('source_id') == item.get('source_id')
                and gap_hours < same_source_hours):
            violations.add('same_source')
        if (candidate.get('topic') and candidate.get('topic') == item.get('topic')
                and gap_hours < same_topic_hours):
            violations.add('same_topic')
    return sorted(violations)
