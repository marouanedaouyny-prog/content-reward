from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix='/api/v1/clipping/trends', tags=['Trending research'])


def agent(request: Request):
    return request.app.state.trend_agent


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ScheduleRequest(EmptyRequest):
    enabled: bool


class ScanRequest(EmptyRequest):
    auto_preview: bool = False


class PreviewRequest(EmptyRequest):
    candidate_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{11}$')


@router.get('')
def status(research=Depends(agent)):
    return research.status()


@router.post('/runs', status_code=202)
def scan(body: ScanRequest, research=Depends(agent)):
    if body.auto_preview:
        research.set_enabled(True)
    return research.request_scan(auto_preview=body.auto_preview)


@router.get('/runs/{run_id}')
def report(run_id: str, research=Depends(agent)):
    return research.get(run_id)


@router.post('/schedule')
def schedule(body: ScheduleRequest, research=Depends(agent)):
    return research.set_enabled(body.enabled)


@router.post('/runs/{run_id}/preview', status_code=202)
def preview(run_id: str, body: PreviewRequest, research=Depends(agent)):
    return research.preview(run_id, body.candidate_id)


def trends_script():
    return FileResponse(Path(__file__).with_name('trends.js'), media_type='text/javascript')
