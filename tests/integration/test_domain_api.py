import httpx
import pytest
from datetime import datetime, timedelta, timezone


@pytest.mark.asyncio
async def test_domain_routes_use_typed_orders_campaigns_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPPING_DATABASE', str(tmp_path / 'jobs.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(tmp_path / 'storage'))
    monkeypatch.setenv('CLIPPING_TREND_AGENT', 'false')
    from clipping.app import app
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.post('/orders', json={'target': 20})
        assert response.status_code == 202, response.text
        order = response.json()
        assert order['status'] == 'created' and order['requested_clip_count'] == 20
        assert (await client.get('/orders')).json()[0]['id'] == order['id']
        campaign = await client.post('/campaigns', json={'title': 'Reviewed later', 'platform': 'youtube'})
        assert campaign.status_code == 201
        assert (await client.get('/campaigns')).json()[0]['rights_confirmed'] is False
        metrics = (await client.get('/metrics')).json()
        assert metrics['clips_generated'] == 0 and metrics['reward_per_clip'] is None
        insights = (await client.get('/growth-insights')).json()
        assert insights['status'] == 'insufficient_data'
        assert insights['minimum_independent_clips'] == 3
        assert (await client.get('/clips')).json() == []
        library = (await client.get('/niche-library')).json()
        assert library['publishing_enabled'] is False
        assert {'sports', 'streams', 'business', 'education'} <= {item['id'] for item in library['categories']}
        assert all(item['available_clip_count'] == 0 for item in library['categories'])
        assert (await client.post('/orders', json={'target': -1})).status_code == 422
        learning_context = {'account_id': 'local-account', 'reporting_window_hours': 24.0,
                            'view_definition': 'engaged_views', 'definition_version': '2026-08-24'}
        contextual = (await client.post('/orders', json={'target': 20, 'measurement_context': learning_context})).json()
        assert app.state.domain_store.get_order(contextual['id'])['config']['measurement_context'] == learning_context
        assert (await client.post('/orders', json={'measurement_context': {'reporting_window_hours': -1}})).status_code == 422
        assert (await client.post('/orders', json={'target': 20}, headers={'Origin': 'https://untrusted.example'})).status_code == 403


@pytest.mark.asyncio
async def test_local_queue_and_posting_time_routes_never_publish(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPPING_DATABASE', str(tmp_path / 'jobs.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(tmp_path / 'storage'))
    monkeypatch.setenv('CLIPPING_TREND_AGENT', 'false')
    from clipping.app import app
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        order = (await client.post('/orders', json={'target': 1})).json()
        app.state.domain_store.save_clip({
            'id': 'queueable-clip', 'order_id': order['id'], 'path': 'clip.mp4',
            'sha256': 'a' * 64, 'status': 'READY',
            'settings': {'topic': 'business'},
        })
        clip_record = (await client.get('/clips/queueable-clip')).json()
        assert clip_record['status'] == 'READY' and clip_record['available'] is False
        assert clip_record['missing_artifacts'] == ['video', 'subtitles', 'post_caption']
        observed = await client.post('/metrics', json={
            'clip_id': 'queueable-clip', 'platform': 'instagram', 'views': 1200,
            'followers_generated': 4, 'hashtags': ['#Business', '#CreatorTips'],
        })
        assert observed.status_code == 201, observed.text
        from analytics.collectors import latest_performance
        assert latest_performance(app.state.domain_store)[0].hashtags == ['#Business', '#CreatorTips']
        scheduled_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        queued = await client.post('/queue', json={
            'clip_id': 'queueable-clip', 'platform': 'instagram', 'scheduled_at': scheduled_at,
            'caption': 'Review this clip', 'hashtags': ['#business'], 'cta': 'none',
        })
        assert queued.status_code == 201, queued.text
        assert queued.json()['status'] == 'SCHEDULED'
        assert (await client.get('/queue')).json()[0]['clip_id'] == 'queueable-clip'
        timing = (await client.get('/posting-time/instagram')).json()
        assert timing['basis'] == 'configured_fallback'
        with app.state.domain_store.connection() as db:
            assert db.execute("SELECT count(*) FROM publications WHERE status='PUBLISHED'").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_hashtag_suggestions_learn_from_measured_tags_without_publishing(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPPING_DATABASE', str(tmp_path / 'jobs.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(tmp_path / 'storage'))
    monkeypatch.setenv('CLIPPING_TREND_AGENT', 'false')
    from clipping.app import app
    from analytics.collectors import collect_performance
    from analytics.models import ClipPerformance
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        order = (await client.post('/orders', json={'target': 1})).json()
        store = app.state.domain_store
        import hashlib
        context = {'account_id': 'local-review-account', 'reporting_window_hours': 24.0,
                   'view_definition': 'engaged_views', 'definition_version': '2026-08-24'}
        for tag, followers in (('#growth', 10), ('#stale', 0)):
            for index in range(3):
                clip_id = f'{tag[1:]}-{index}'
                store.save_clip({'id': clip_id, 'order_id': order['id'], 'path': 'clip.mp4',
                    'sha256': hashlib.sha256(clip_id.encode()).hexdigest(), 'status': 'READY',
                    'settings': {'delivery_niche': 'business'}})
                collect_performance(store, ClipPerformance(clip_id=clip_id, platform='instagram',
                    views=1000, followers_generated=followers, hashtags=[tag], measurement_context=context))

        response = await client.post('/hashtags/suggest', json={
            'platform': 'instagram', 'niche_keywords': ['business'],
            'topic_keywords': ['growth', 'stale', 'startup'], 'clip_topic': 'growth startup business',
            'measurement_context': context, 'niche': 'business',
        })

        assert response.status_code == 200, response.text
        result = response.json()
        assert result['history_status'] == 'measured'
        assert result['suggestion']['scores']['#growth']['account_history'] > \
            result['suggestion']['scores']['#stale']['account_history']
        assert (await client.get('/growth-insights')).json()['reason'] == 'learning_context_required'
        scoped = await client.get('/growth-insights', params={**context, 'platform': 'instagram', 'niche': 'business'})
        assert scoped.status_code == 200 and scoped.json()['status'] == 'measured'
        assert scoped.json()['cohort'] == {'platform': 'instagram', 'niche': 'business'}
        assert (await client.get('/growth-insights', params={'as_of': '2026-10-22T00:00:00'})).status_code == 422
        with store.connection() as db:
            assert db.execute("SELECT count(*) FROM publications WHERE status='PUBLISHED'").fetchone()[0] == 0
