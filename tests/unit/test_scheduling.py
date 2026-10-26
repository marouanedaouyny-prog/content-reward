from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest


def test_posting_time_uses_history_only_after_minimum_sample_count():
    from growth.timing import PostingTimeOptimizer

    now = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
    history = [
        {'platform': 'instagram', 'posted_at': datetime(2026, month, day, 19,
            tzinfo=ZoneInfo('Africa/Casablanca')).isoformat(), 'views': 1000, 'followers_gained': 20}
        for month, day in ((9, 16), (9, 23), (9, 30), (10, 7), (10, 14))
    ]
    history.append({'platform': 'instagram', 'posted_at': '2026-10-28T19:00:00+00:00',
                    'views': 1000, 'followers_gained': 1000})
    result = PostingTimeOptimizer(minimum_samples=5).recommend(
        'instagram', history, timezone_name='Africa/Casablanca',
        default_windows=['12:00-14:00'], now=now)

    assert result['basis'] == 'account_history'
    assert result['followers_per_1000_views'] == 20
    assert result['recommended_at'].hour == 19
    assert result['recommended_at'].tzinfo is not None


def test_posting_time_uses_configured_cold_start_windows():
    from growth.timing import PostingTimeOptimizer

    now = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
    result = PostingTimeOptimizer().recommend(
        'tiktok', [], timezone_name='Africa/Casablanca',
        default_windows=['12:00-14:00', '18:00-22:00'], now=now)

    assert result['basis'] == 'configured_fallback'
    assert result['recommended_at'].hour == 12
    assert result['timezone'] == 'Africa/Casablanca'


def test_content_spacing_reports_daily_gap_source_and_topic_conflicts():
    from growth.timing import content_spacing_violations

    scheduled = datetime(2026, 10, 20, 18, tzinfo=timezone.utc)
    existing = [
        {'scheduled_at': '2026-10-20T16:00:00+00:00', 'source_id': 'source-a', 'topic': 'business'},
        {'scheduled_at': '2026-10-20T13:00:00+00:00', 'source_id': 'source-b', 'topic': 'business'},
    ]
    violations = content_spacing_violations(
        {'scheduled_at': scheduled, 'source_id': 'source-a', 'topic': 'business'},
        existing, max_posts_per_day=3, minimum_gap_minutes=180,
        same_source_hours=8, same_topic_hours=6)

    assert set(violations) == {'minimum_gap', 'same_source', 'same_topic'}


def test_schedule_queue_persists_review_only_entries_and_limits_list(tmp_path):
    from test_publishing import prepared

    store, _, _ = prepared(tmp_path)
    scheduled = datetime.now(timezone.utc) + timedelta(days=1)
    result = store.enqueue_post({
        'id': 'queue-1', 'clip_id': 'clip', 'platform': 'instagram',
        'scheduled_at': scheduled.isoformat(), 'caption': 'Review this clip',
        'hashtags': ['#business'], 'cta': 'none', 'account_id': None,
    })

    assert result['status'] == 'SCHEDULED'
    assert result['account_id'] is None
    assert store.list_post_queue(status='SCHEDULED')[0]['clip_id'] == 'clip'
    assert store.list_post_queue(status='PUBLISHED') == []


def test_schedule_queue_rejects_unknown_clip_and_invalid_platform(tmp_path):
    from app.repositories.store import Store

    store = Store(tmp_path / 'domain.db')
    record = {'id': 'queue-1', 'clip_id': 'missing', 'platform': 'unknown',
              'scheduled_at': '2026-10-21T12:00:00+00:00', 'caption': '',
              'hashtags': [], 'cta': 'none', 'account_id': None}
    with pytest.raises(ValueError):
        store.enqueue_post(record)


def test_schedule_queue_enforces_spacing_against_saved_review_entries(tmp_path):
    from test_publishing import prepared

    store, _, _ = prepared(tmp_path)
    clip = store.get_clip('clip')
    store.save_clip({**clip, 'settings': clip['settings'] | {'topic': 'business'}})
    future = datetime.now(timezone.utc) + timedelta(days=2)
    store.enqueue_post({'id': 'queue-1', 'clip_id': 'clip', 'platform': 'instagram',
        'scheduled_at': future.isoformat(), 'caption': 'First', 'hashtags': [], 'cta': 'none'})
    with pytest.raises(ValueError, match='same_topic'):
        store.enqueue_post({'id': 'queue-2', 'clip_id': 'clip', 'platform': 'instagram',
            'scheduled_at': (future + timedelta(hours=4)).isoformat(), 'caption': 'Second',
            'hashtags': [], 'cta': 'none'})


def test_posting_history_requires_actual_publication_evidence(tmp_path):
    import json
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    from app.repositories.database import timestamp
    from test_publishing import prepared

    store, _, _ = prepared(tmp_path)
    collect_performance(store, ClipPerformance(clip_id='clip', platform='instagram', views=1000,
        followers_generated=50))
    now = timestamp()
    with store.connection(write=True) as db:
        db.execute('INSERT INTO publications VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            ('publication-1', 'clip', 'instagram', 'READY', 'key-1', 'hash', None, None,
             now, now, json.dumps({'adapter': 'manual', 'network_attempted': False}), None))
    assert store.posting_history('instagram') == []

    with store.connection(write=True) as db:
        db.execute("UPDATE publications SET status='PUBLISHED',metadata=? WHERE id=?",
            (json.dumps({'adapter': 'instagram', 'network_attempted': True,
                         'published_at': '2026-10-19T19:00:00+01:00'}), 'publication-1'))
    assert store.posting_history('instagram') == [{
        'platform': 'instagram', 'posted_at': '2026-10-19T19:00:00+01:00',
        'views': 1000, 'followers_gained': 50,
    }]
