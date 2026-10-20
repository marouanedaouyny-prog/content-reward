import importlib
import asyncio
import shutil
import time
from pathlib import Path
import uuid

import httpx
import pytest


@pytest.mark.asyncio
async def test_api_queues_approvals_and_rejects_unsafe_upload_paths(monkeypatch):
    assert Path('clipping/app.py').exists(), 'Clipping API is missing'
    folder = Path('.workflow-tests') / uuid.uuid4().hex
    folder.mkdir(parents=True)
    monkeypatch.setenv('CLIPPING_DATABASE', str(folder / 'api.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(folder / 'storage'))
    app = importlib.import_module('clipping.app').app
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver'
    ) as client:
        assert (await client.get('/')).status_code == 200
        payload = {'campaign': {'title': 'Campaign', 'url': 'https://contentrewards.com/discover',
                   'platform': 'youtube', 'rights_notes': 'Authorized brand assets',
                   'rules': 'Vertical clips'}, 'dry_run': True,
                   'clip_plan': {'duration_seconds': 5}}
        response = await client.post('/api/v1/clipping/jobs', json={'payload': payload})
        assert response.status_code == 202, response.text
        job = response.json()
        assert job['status'] == 'awaiting_campaign_approval'
        assert (await client.get('/api/v1/jobs')).json()['jobs'][0]['id'] == job['id']
        bad = await client.post(f"/api/v1/jobs/{job['id']}/approve", json={
            'step_name': 'clip_review', 'fingerprint': job['approval_fingerprint'], 'approved': True})
        assert bad.status_code == 409
        foreign_origin = await client.post('/api/v1/clipping/jobs', json={'payload': payload},
                                     headers={'Origin': 'https://untrusted.example'})
        assert foreign_origin.status_code == 403
        upload = await client.post('/api/v1/clipping/uploads', files={'file': ('source.mp4', b'not media', 'video/mp4')})
        assert upload.status_code == 201
        assert upload.json()['source_path'].startswith('uploads/')
        unsafe = payload | {'source_path': '../outside.mp4'}
        assert (await client.post('/api/v1/clipping/jobs', json={'payload': unsafe})).status_code == 422
        assert (await client.get(f"/api/v1/jobs/{job['id']}/artifacts/clip")).status_code == 404
        cancel = await client.post(f"/api/v1/jobs/{job['id']}/cancel")
        assert cancel.json()['status'] == 'cancelled'


@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
async def test_native_worker_prepares_direct_jobs_and_resumes_after_review(monkeypatch):
    folder = Path('.workflow-tests') / uuid.uuid4().hex
    folder.mkdir(parents=True)
    monkeypatch.setenv('CLIPPING_DATABASE', str(folder / 'api.db'))
    monkeypatch.setenv('CLIPPING_STORAGE', str(folder / 'storage'))
    app = importlib.import_module('clipping.app').app
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://testserver'
    ) as client:
        payload = {'campaign': {'title': 'Direct workflow', 'url': 'https://contentrewards.com/discover',
                   'platform': 'youtube', 'rights_notes': 'Synthetic practice footage',
                   'rules': 'Vertical practice clip'}, 'dry_run': True,
                   'clip_plan': {'duration_seconds': 1, 'aspect_ratio': '9:16'}}
        response = await client.post('/api/v1/clipping/jobs', json={'payload': payload})
        assert response.status_code == 202
        job = response.json()
        base = f"/api/v1/jobs/{job['id']}"

        async def approve_current(current):
            response = await client.post(base + '/approve', json={
                'step_name': current['waiting_step'],
                'fingerprint': current['approval_fingerprint'], 'approved': True})
            assert response.status_code == 200, response.text

        async def wait_for_status(expected):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                health = await client.get('/health')
                assert health.status_code == 200
                current = (await client.get(base)).json()
                assert current['status'] not in ('failed', 'blocked', 'cancelled'), current
                if current['status'] == expected:
                    return current
                await asyncio.sleep(.1)
            pytest.fail(f'Built-in worker did not reach {expected}')

        await approve_current(job)
        reviewed = await wait_for_status('awaiting_clip_approval')
        assert all(reviewed['output']['quality']['checks'].values())
        clip = await client.get(base + '/artifacts/clip')
        assert clip.status_code == 200 and len(clip.content) > 1024
        await approve_current(reviewed)
        completed = await wait_for_status('completed')
        assert completed['output']['dry_run'] is True
        assert 'publication' not in completed['output']
        assert 'submission' not in completed['output']
