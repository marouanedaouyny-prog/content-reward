from datetime import datetime, timedelta, timezone

import pytest

from test_publishing import prepared


def test_metrics_persist_unknowns_and_refuse_invalid_values(tmp_path):
    from analytics.models import ClipPerformance
    from analytics.collectors import collect_performance, latest_performance
    store, _, _ = prepared(tmp_path)
    observation = ClipPerformance(clip_id='clip', platform='youtube', views=100, likes=5,
                                  completion_rate=.8, reward_amount='1.25')
    collect_performance(store, observation)
    assert latest_performance(store)[0].saves is None
    assert str(latest_performance(store)[0].reward_amount) == '1.25'
    with pytest.raises(ValueError):
        ClipPerformance(clip_id='clip', platform='youtube', completion_rate=1.5)
    with pytest.raises(ValueError):
        ClipPerformance(clip_id='clip', platform='youtube', views=-1)


def test_feedback_needs_independent_clips_and_counts_latest_snapshot_only(tmp_path):
    from analytics.models import ClipPerformance
    from analytics.collectors import collect_performance
    from analytics.feedback import feedback_adjustment
    store, _, path = prepared(tmp_path)
    now = datetime.now(timezone.utc)
    for i in range(8):
        collect_performance(store, ClipPerformance(clip_id='clip', platform='youtube', views=500,
            completion_rate=.9, collected_at=(now + timedelta(seconds=i)).isoformat()))
    assert feedback_adjustment(store, caption_style='studio')['adjustment'] == 0
    for index in range(1, 6):
        first = store.get_clip('clip')
        store.save_clip({**first, 'id': 'clip-' + str(index), 'path': str(path)})
        collect_performance(store, ClipPerformance(clip_id='clip-' + str(index), platform='youtube',
            views=1000, completion_rate=.9))
    report = feedback_adjustment(store, caption_style='studio')
    assert report['samples'] == 6
    assert 0 < report['adjustment'] <= .1
    assert report['basis']


def test_business_metrics_report_unknown_reward_and_publish_rates(tmp_path):
    from analytics.reports import business_metrics
    store, _, _ = prepared(tmp_path)
    report = business_metrics(store)
    assert report['clips_generated'] == 1
    assert report['publish_success_rate'] is None
    assert report['reward_per_clip'] is None
