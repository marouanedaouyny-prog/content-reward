import importlib
import json
import shutil
import uuid
from pathlib import Path

import httpx
import pytest

SRT = '1\n00:00:00,000 --> 00:00:02,000\nWhy choose this moment?\n\n2\n00:00:02,000 --> 00:00:05,000\nReview the complete result.\n'


@pytest.mark.asyncio
async def test_research_routes_support_demo_samples_and_editable_plans(monkeypatch):
    folder = Path('.workflow-tests') / uuid.uuid4().hex
    monkeypatch.setenv('CLIPPING_DATABASE', str(folder / 'api.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(folder / 'storage'))
    app = importlib.import_module('clipping.app').app
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver'
    ) as client:
        base = '/api/v1/clipping/research'
        demo = await client.get(base + '/demo')
        assert demo.status_code == 200
        assert demo.json()['source'] == 'synthetic_demo'
        assert demo.json()['cohorts']
        assert demo.json()['planning_brief']['can_apply'] is False
        content = b'content_id,create_time,desc,duration,views\n7500000000000000001,2025-08-01T00:00:00Z,AI,20,5\n'
        sample = await client.post(base + '/reports', files={'file': ('sample.csv', content)},
                                   data={'keywords': 'AI'})
        assert sample.status_code == 200, sample.text
        assert sample.json()['valid_records'] == 1
        assert sample.json()['cohorts'] == []
        assert sample.json()['planning_brief'] is None
        assert sample.json()['brief_note']
        bad = await client.post(base + '/reports', files={'file': ('data.parquet', b'not a text sample')})
        assert bad.status_code == 422
        plan = await client.post(base + '/plans', json={'transcript_srt': SRT,
                                'target_duration': 5, 'min_duration': 1, 'max_duration': 5})
        assert plan.status_code == 200, plan.text
        assert plan.json()[0]['score_type'] == 'editorial_heuristic'
        assert (await client.get('/research.js')).status_code == 200
        studio = await client.get('/studio.js')
        assert studio.status_code == 200
        assert 'javascript' in studio.headers['content-type']
        assert 'clipForm' in studio.text
        assert 'Choose a YouTube source' in (await client.get('/')).text
        rejected = await client.post(base + '/plans', json={'transcript_srt': SRT},
                                     headers={'Origin': 'https://foreign.example'})
        assert rejected.status_code == 403
        assert (await client.get('/api/v1/jobs')).json()['jobs'] == []


@pytest.mark.asyncio
async def test_source_route_validates_url_and_returns_only_public_details(monkeypatch):
    from clipping import media
    monkeypatch.setattr(media, 'command', lambda *a, **k: json.dumps(
        {'title': 'An authorized source', 'uploader': 'Creator', 'duration': 60}))
    app = importlib.import_module('clipping.app').app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        endpoint = '/api/v1/clipping/research/sources'
        assert (await client.post(endpoint, json={'url': 'https://evil.example/video'})).status_code == 422
        response = await client.post(endpoint, json={'url': 'https://youtu.be/abcdefghijk'})
        assert response.status_code == 200
        assert response.json()['duration'] == 60
        assert 'token' not in response.text


@pytest.mark.asyncio
async def test_source_timeout_returns_an_actionable_service_error(monkeypatch):
    import subprocess
    from clipping import media
    def unavailable(*args, **kwargs):
        raise subprocess.TimeoutExpired('yt-dlp', 45)
    monkeypatch.setattr(media, 'command', unavailable)
    app = importlib.import_module('clipping.app').app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.post('/api/v1/clipping/research/sources',
                                     json={'url': 'https://youtu.be/abcdefghijk'})
        assert response.status_code == 503
        assert 'uploaded source' in response.json()['detail']


@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
async def test_automatic_cut_renders_and_downloads_suggestions_after_approval(monkeypatch):
    import asyncio
    import time
    folder = Path('.workflow-tests') / uuid.uuid4().hex
    monkeypatch.setenv('CLIPPING_DATABASE', str(folder / 'api.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(folder / 'storage'))
    app = importlib.import_module('clipping.app').app
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver'
    ) as client:
        records = [dict(content_id=str(1000 + index), create_time='2025-08-01T00:00:00Z',
                        desc='Complete result', duration=5, views=100, shares=2,
                        language='en', country='US') for index in range(10)]
        report = await client.post('/api/v1/clipping/research/reports',
                                   files={'file': ('fixture.jsonl', '\n'.join(json.dumps(row) for row in records).encode())},
                                   data={'keywords': 'result'})
        assert report.status_code == 200, report.text
        brief = report.json()['planning_brief']
        assert brief['can_apply'] and brief['basis'] == 'sample_support'
        payload = {'campaign': {'title': 'Automatic demo', 'url': 'https://example.com/campaign',
                   'rights_notes': 'Synthetic demo footage', 'rules': 'Complete five-second cut',
                   'platform': 'tiktok', 'duration_min': 1, 'duration_max': 5}, 'dry_run': True,
                   'auto_clip': True, 'transcript_srt': SRT,
                   'research_keywords': ', '.join(brief['keywords']),
                   'clip_plan': {'duration_seconds': brief['target_duration']}}
        job = (await client.post('/api/v1/clipping/jobs', json={'payload': payload})).json()
        base = f"/api/v1/jobs/{job['id']}"
        assert job['status'] == 'awaiting_campaign_approval'
        await client.post(base + '/approve', json={'step_name': job['waiting_step'],
                         'fingerprint': job['approval_fingerprint'], 'approved': True})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = (await client.get(base)).json()
            assert job['status'] != 'failed', job
            if job['status'] == 'awaiting_clip_approval':
                break
            await asyncio.sleep(.1)
        assert job['status'] == 'awaiting_clip_approval'
        assert job['output']['selected_clip_plan']['duration_seconds'] == 5
        assert all(job['output']['quality']['checks'].values())
        assert len((await client.get(base + '/artifacts/clip')).content) > 1024
        ideas = await client.get(base + '/artifacts/ideas')
        assert ideas.status_code == 200 and ideas.json()['suggestions']
        package = (await client.get(base + '/artifacts/package')).json()
        assert package['clip_plan'] == job['output']['selected_clip_plan']
        assert 'publication' not in job['output']
