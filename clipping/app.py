"""Local clipping API and browser workspace. Run: python -m uvicorn clipping.app:app."""

import asyncio
import importlib.util
import logging
import os
import shutil
import threading
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from clipping.workflow import ClippingWorkflow
from clipping.research_api import router as research_router, research_script
from clipping.trends import TrendResearchAgent
from clipping.trends_api import router as trends_router, trends_script
from clipping.instagram import InstagramConnection
from clipping.instagram_api import router as instagram_router, instagram_script

logger = logging.getLogger(__name__)
ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000',
           'http://localhost:3000', 'http://127.0.0.1:3000', 'http://testserver']


@asynccontextmanager
async def lifespan(app):
    workflow = ClippingWorkflow(os.environ.get('CLIPPING_DATABASE', 'data/clipping.db'),
                                os.environ.get('CLIPPING_STORAGE', 'storage/clipping'))
    app.state.workflow = workflow
    app.state.trend_agent = TrendResearchAgent(workflow)
    app.state.instagram = InstagramConnection(workflow)
    stop = threading.Event()
    workflow.recover_interrupted()
    if os.environ.get('CLIPPING_AUTOMATION') == 'ishowspeed':
        workflow.create_automatic_preview()
    elif os.environ.get('CLIPPING_AUTOMATION') == 'trends':
        app.state.trend_agent.set_enabled(True)
        app.state.trend_agent.request_scan(auto_preview=True)

    def consume():
        while not stop.is_set():
            try:
                if workflow.consume_once():
                    continue
            except Exception:
                logger.exception('Clipping queue consumer failed')
            stop.wait(1)

    def research():
        while not stop.is_set():
            try:
                app.state.trend_agent.consume_once()
            except Exception:
                logger.exception('Trend research consumer failed')
            stop.wait(5)

    async def maintain_leases():
        while True:
            await asyncio.sleep(10)
            await asyncio.to_thread(workflow.heartbeat)
            await asyncio.to_thread(workflow.recover_interrupted)

    worker = threading.Thread(target=consume, name='clipping-worker', daemon=True)
    worker.start()
    researcher = None
    if os.environ.get('CLIPPING_TREND_AGENT', 'true').lower() not in ('false', '0', 'no'):
        researcher = threading.Thread(target=research, name='trend-research-agent', daemon=True)
        researcher.start()
    heartbeat = asyncio.create_task(maintain_leases())
    try:
        yield
    finally:
        stop.set()
        workflow.shutdown_requested = True
        await asyncio.to_thread(worker.join, 5)
        if researcher:
            await asyncio.to_thread(researcher.join, 5)
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


app = FastAPI(title='Clipping Workflow', version='1.0.0', lifespan=lifespan)
app.include_router(research_router)
app.include_router(trends_router)
app.include_router(instagram_router)
app.add_api_route('/research.js', research_script, methods=['GET'], include_in_schema=False)
app.add_api_route('/trends.js', trends_script, methods=['GET'], include_in_schema=False)
app.add_api_route('/instagram.js', instagram_script, methods=['GET'], include_in_schema=False)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET', 'POST'],
                   allow_headers=['Content-Type'])


@app.middleware('http')
async def restrict_browser_origins(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        local_origin = f'{request.url.scheme}://{request.url.netloc}'
        if origin and origin not in ORIGINS and origin != local_origin:
            return JSONResponse({'detail': 'Use the local clipping workspace'}, status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def invalid_transition(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409)


@app.exception_handler(KeyError)
async def missing_resource(request, exc):
    return JSONResponse({'detail': str(exc.args[0])}, status_code=404)


def workflow(request: Request):
    return request.app.state.workflow


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class JobRequest(InputModel):
    workflow_id: Literal['content_rewards'] = 'content_rewards'
    payload: dict[str, Any]
    idempotency_key: str | None = None


class AutomaticPreviewRequest(InputModel):
    """No source, niche, timing, format or subtitle choices are required."""


class Approval(InputModel):
    step_name: Literal['campaign_review', 'clip_review']
    fingerprint: str
    approved: bool
    approver: str = 'local operator'
    brand_draft_reference: str | None = None


class Transcript(InputModel):
    srt: str = Field(min_length=1, max_length=2_000_000)


class Publication(InputModel):
    post_url: str
    public_confirmed: bool
    published_at: str


class Submission(InputModel):
    reference: str
    submitted_at: str


class Reward(InputModel):
    status: Literal['pending_review', 'approved', 'rejected', 'flagged', 'paid']
    reference: str
    amount: float | None = None


class KillSwitch(InputModel):
    enabled: bool


@app.get('/')
def workspace():
    return FileResponse(Path(__file__).with_name('workspace.html'), media_type='text/html')


@app.get('/studio.js', include_in_schema=False)
def studio_script():
    return FileResponse(Path(__file__).with_name('studio.js'), media_type='text/javascript')


@app.get('/health')
def health(engine=Depends(workflow)):
    from clipping.media import model_files_ready, whisper_model_location

    return {'status': 'healthy', 'version': '1.0.0', 'kill_switch': engine.killed(),
            'tools': {name: bool(shutil.which(name)) for name in ('ffmpeg', 'ffprobe', 'yt-dlp')},
            'transcription_installed': importlib.util.find_spec('faster_whisper') is not None,
            'english_model_ready': model_files_ready(Path(whisper_model_location(engine.storage, 'en'))),
            'multilingual_model_ready': model_files_ready(Path(whisper_model_location(engine.storage)))}


@app.get('/examples/practice.srt')
def sample_subtitles():
    return FileResponse(Path(__file__).parent / 'examples' / 'practice.srt',
                        media_type='application/x-subrip', filename='practice.srt')


@app.post('/api/v1/clipping/jobs', status_code=202)
@app.post('/api/v1/workflows/content_rewards/run', status_code=202)
def create_job(body: JobRequest, engine=Depends(workflow)):
    try:
        return engine.create(body.payload, body.idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/api/v1/jobs')
def list_jobs(limit: int = 50, engine=Depends(workflow)):
    return {'jobs': engine.list(limit)}


@app.post('/api/v1/clipping/automations/ishowspeed/runs', status_code=202)
def automatic_preview(body: AutomaticPreviewRequest | None = None, engine=Depends(workflow)):
    try:
        return engine.create_automatic_preview()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/api/v1/jobs/{job_id}')
def get_job(job_id: str, engine=Depends(workflow)):
    return engine.get(job_id)


@app.post('/api/v1/jobs/{job_id}/approve')
def approve(job_id: str, body: Approval, engine=Depends(workflow)):
    return engine.approve(job_id, body.step_name, body.fingerprint, body.approved,
                          body.approver, body.brand_draft_reference)


@app.post('/api/v1/jobs/{job_id}/transcript')
def provide_transcript(job_id: str, body: Transcript, engine=Depends(workflow)):
    return engine.provide_transcript(job_id, body.srt)


@app.post('/api/v1/jobs/{job_id}/publication')
def confirm_publication(job_id: str, body: Publication, engine=Depends(workflow)):
    return engine.record_publication(job_id, body.post_url, body.public_confirmed, body.published_at)


@app.post('/api/v1/jobs/{job_id}/submission')
def confirm_submission(job_id: str, body: Submission, engine=Depends(workflow)):
    return engine.record_submission(job_id, body.reference, body.submitted_at)


@app.post('/api/v1/jobs/{job_id}/reward')
def record_reward(job_id: str, body: Reward, engine=Depends(workflow)):
    return engine.record_reward(job_id, body.status, body.reference, body.amount)


@app.post('/api/v1/jobs/{job_id}/cancel')
def cancel(job_id: str, engine=Depends(workflow)):
    return engine.cancel(job_id)


@app.post('/api/v1/jobs/{job_id}/retry', status_code=202)
def retry(job_id: str, engine=Depends(workflow)):
    return engine.retry(job_id)


@app.post('/api/v1/system/kill-switch')
def kill_switch(body: KillSwitch, engine=Depends(workflow)):
    engine.set_kill_switch(body.enabled)
    return {'enabled': engine.killed()}


@app.get('/api/v1/jobs/{job_id}/artifacts/{kind}')
def artifact(job_id: str, kind: str, engine=Depends(workflow)):
    path = engine.artifact(job_id, kind)
    if not path.is_file():
        raise HTTPException(status_code=404, detail='Artifact file missing')
    return FileResponse(path, filename=path.name)


@app.post('/api/v1/clipping/uploads', status_code=201)
def upload(file: UploadFile = File(...), engine=Depends(workflow)):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ('.mp4', '.mov', '.mkv', '.webm'):
        raise HTTPException(status_code=422, detail='Upload MP4, MOV, MKV, or WebM video')
    folder = engine.storage / 'uploads'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{uuid.uuid4().hex}{suffix}'
    size = 0
    try:
        with path.open('wb') as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > 500 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail='Source video exceeds 500 MB')
                target.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail='Source file is empty')
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()
    return {'source_path': path.relative_to(engine.storage).as_posix(), 'size_bytes': size}
