"""Local source inspection, metadata reports and editable transcript plans."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from clipping import planning, research
from clipping.media import parse_srt

router = APIRouter(prefix='/api/v1/clipping/research', tags=['Clip research'])


class ResearchInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class SourceRequest(ResearchInput):
    url: str = Field(max_length=2000)


class SourceDetails(BaseModel):
    url: str
    title: str
    creator: str
    duration: float
    note: str


class Cohort(BaseModel):
    topic: str
    month: str
    language: str
    country: str
    duration_min: int
    duration_max: int
    count: int
    median_duration: float
    median_views: float
    share_observations: int
    save_observations: int
    median_share_rate: float | None
    median_save_rate: float | None


class PlanningBrief(BaseModel):
    topic: str
    keywords: list[str]
    target_duration: float
    month: str
    language: str
    country: str
    support_count: int
    compared_cohorts: int
    basis: Literal['share_rate', 'sample_support']
    median_share_rate: float | None
    can_apply: bool
    reason: str
    note: str


class MetadataReport(BaseModel):
    source: Literal['operator_sample', 'synthetic_demo']
    input_records: int
    valid_records: int
    invalid_records: int
    duplicate_records: int
    matched_records: int
    empty_captions: int
    keywords: list[str]
    minimum_cohort_size: int
    supported_cohorts: int
    cohorts: list[Cohort]
    planning_brief: PlanningBrief | None
    brief_note: str
    limitations: list[str]
    note: str


class PlanRequest(ResearchInput):
    transcript_srt: str = Field(min_length=1, max_length=2_000_000)
    source_duration: float | None = Field(default=None, gt=0)
    target_duration: float = Field(default=30, ge=1, le=180)
    min_duration: float = Field(default=15, ge=1, le=180)
    max_duration: float = Field(default=60, ge=1, le=180)
    keywords: str = Field(default='', max_length=200)


class ClipPlan(BaseModel):
    start_seconds: float
    duration_seconds: float
    aspect_ratio: Literal['9:16', '16:9', '1:1']


class ClipIdea(BaseModel):
    clip_plan: ClipPlan
    editorial_score: float
    score_type: Literal['editorial_heuristic']
    reasons: list[str]
    source_excerpt: str
    caption: str
    note: str


@router.post('/sources', response_model=SourceDetails)
def source_details(body: SourceRequest):
    try:
        url = planning.youtube_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return planning.inspect_youtube(url)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/demo', response_model=MetadataReport)
def demo():
    return research.demo_report()


@router.post('/reports', response_model=MetadataReport)
def metadata_report(file: UploadFile = File(...), keywords: str = Form('', max_length=200),
                    country: str = Form('', max_length=12), language: str = Form('', max_length=12)):
    try:
        content = file.file.read(research.MAX_BYTES + 1)
        return research.analyze_metadata(content, file.filename or '', keywords, country, language)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        file.file.close()


@router.post('/plans', response_model=list[ClipIdea])
def clip_plans(body: PlanRequest):
    try:
        segments = parse_srt(body.transcript_srt)
        duration = body.source_duration or max(segment['end'] for segment in segments)
        return planning.suggest_cuts(segments, duration, body.target_duration,
                                     body.min_duration, body.max_duration, body.keywords)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def research_script():
    return FileResponse(Path(__file__).with_name('research.js'), media_type='text/javascript')
