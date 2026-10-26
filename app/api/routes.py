from typing import Literal
from datetime import datetime
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import Field, field_validator

from analytics.collectors import collect_performance
from analytics.models import ClipPerformance, MeasurementContext
from analytics.reports import business_metrics, growth_insights, observed_hashtag_history
from app.core.config import StrictModel, load_settings
from app.models.domain import ClipSummary, MetricsSummary, OrderSummary, PostQueueEntry
from app.repositories.store import Store
from campaigns.models import Campaign
from campaigns.validation import Eligibility, validate_campaign
from clipping.orchestrator import Config, Controller
from growth.hashtags import HashtagGenerator
from growth.timing import PostingTimeOptimizer

router = APIRouter()


def store(request: Request):
    return request.app.state.domain_store


class OrderRequest(StrictModel):
    target: int | None = Field(default=None, ge=1, le=10000)
    niche: str | None = None
    provider: Literal['public', 'selenium'] = 'public'
    campaign_id: str | None = None
    measurement_context: MeasurementContext | None = None


class HashtagSuggestionRequest(StrictModel):
    platform: Literal['youtube', 'tiktok', 'instagram']
    niche_keywords: list[str] = Field(default_factory=list, max_length=30)
    topic_keywords: list[str] = Field(default_factory=list, max_length=50)
    clip_topic: str = Field(default='', max_length=500)
    niche: str | None = Field(default=None, max_length=200)
    measurement_context: MeasurementContext | None = None


@router.post('/orders', response_model=OrderSummary, status_code=202)
def create_order(body: OrderRequest, repository: Store = Depends(store)):
    settings = load_settings()
    if body.campaign_id:
        repository.get_campaign(body.campaign_id)
    config = Config(provider=body.provider, niche=body.niche, partial_downloads=True,
                    clip_count=body.target or settings.clips.target_count,
                    clips_per_source=settings.production.clips_per_source,
                    caption_style=settings.production.caption_style, framing_mode=settings.video.framing,
                    duration=settings.clips.target_duration, campaign_id=body.campaign_id,
                    organize_by_niche=True,
                    measurement_context=body.measurement_context.model_dump(mode='json') if body.measurement_context else None)
    controller = Controller(repository.path.parent, config, emit=lambda _: None)
    return OrderSummary.from_state(controller.state)


@router.get('/orders', response_model=list[OrderSummary])
def orders(repository: Store = Depends(store)):
    return [OrderSummary.from_state(state) for state in repository.list_orders()]


@router.get('/orders/{identifier}', response_model=OrderSummary)
def order(identifier: str, repository: Store = Depends(store)):
    return OrderSummary.from_state(repository.get_order(identifier))


@router.post('/orders/{identifier}/resume', response_model=OrderSummary, status_code=202)
def resume(identifier: str, tasks: BackgroundTasks, repository: Store = Depends(store)):
    controller = Controller(repository.path.parent, resume=identifier, emit=lambda _: None)
    tasks.add_task(controller.run)
    return OrderSummary.from_state(controller.state)


@router.get('/clips', response_model=list[ClipSummary])
def clips(repository: Store = Depends(store)):
    from clipping.library import clip_availability
    return [ClipSummary.model_validate(clip | clip_availability(clip)) for clip in repository.list_clips()]


@router.get('/niche-library')
def library(repository: Store = Depends(store)):
    from clipping.library import niche_library
    return niche_library(repository)


@router.get('/clips/{identifier}', response_model=ClipSummary)
def clip(identifier: str, repository: Store = Depends(store)):
    from clipping.library import clip_availability
    saved = repository.get_clip(identifier)
    return ClipSummary.model_validate(saved | clip_availability(saved))


@router.get('/campaigns', response_model=list[Campaign])
def campaigns(repository: Store = Depends(store)):
    return repository.list_campaigns()


@router.post('/campaigns', response_model=Campaign, status_code=201)
def campaign(body: Campaign, repository: Store = Depends(store)):
    return repository.save_campaign(body)


class ValidationRequest(StrictModel):
    clip_id: str
    platform: Literal['youtube', 'tiktok', 'instagram']
    caption: str = ''


@router.post('/campaigns/{identifier}/validate', response_model=Eligibility)
def validate(identifier: str, body: ValidationRequest, repository: Store = Depends(store)):
    campaign = repository.get_campaign(identifier)
    clip = repository.get_clip(body.clip_id)
    return validate_campaign(campaign, dict(source_id=clip['source_id'],
        duration_seconds=clip['settings'].get('source_clip_plan', {}).get('duration_seconds'),
        transcript=clip['settings'].get('transcript', '')), {'caption': body.caption}, body.platform,
        source=clip['settings'].get('source'), for_publication=True)


@router.get('/metrics', response_model=MetricsSummary)
def metrics(repository: Store = Depends(store)):
    return MetricsSummary(**business_metrics(repository))


def report_context(account_id: str | None = None, reporting_window_hours: float | None = None,
                   view_definition: Literal['unknown', 'play_starts', 'engaged_views', 'qualified_views',
                                            'platform_reported'] = 'unknown', definition_version: str | None = None):
    if account_id is None and reporting_window_hours is None and view_definition == 'unknown' and definition_version is None:
        return None
    try:
        return MeasurementContext(account_id=account_id, reporting_window_hours=reporting_window_hours,
                                  view_definition=view_definition, definition_version=definition_version)
    except ValueError as error:
        raise HTTPException(status_code=422, detail='Invalid measurement context') from error


@router.get('/growth-insights')
def measured_growth_insights(repository: Store = Depends(store),
                            context: MeasurementContext | None = Depends(report_context),
                            platform: Literal['youtube', 'instagram', 'tiktok'] | None = None,
                            niche: str | None = None, as_of: datetime | None = None):
    if as_of is not None and as_of.utcoffset() is None:
        raise HTTPException(status_code=422, detail='Observation cutoff must include a timezone')
    return growth_insights(repository, measurement_context=context, platform=platform, niche=niche, as_of=as_of)


@router.post('/hashtags/suggest')
def suggest_hashtags(body: HashtagSuggestionRequest, repository: Store = Depends(store)):
    history = observed_hashtag_history(repository, body.platform,
        measurement_context=body.measurement_context, niche=body.niche)
    settings = load_settings()
    generator = HashtagGenerator(niche_keywords=body.niche_keywords,
        topic_keywords=body.topic_keywords, account_history=history['scores'],
        recent_posts=history['recent_posts'], config=settings.hashtags.model_dump())
    suggestion = generator.generate(clip_topic=body.clip_topic, platform=body.platform)
    return {'action': 'review_only', 'history_status': history['status'],
            'history_reason': history.get('reason'), 'measurement_context': history.get('measurement_context'),
            'cohort': history.get('cohort'),
            'minimum_independent_clips': history['minimum_independent_clips'],
            'history_by_tag': history['tags'], 'suggestion': suggestion,
            'limitations': history['limitations']}


@router.post('/metrics', status_code=201)
def observation(body: ClipPerformance, repository: Store = Depends(store)) -> dict[str, str]:
    try:
        return {'observation_id': collect_performance(repository, body)}
    except ValueError as error:
        raise HTTPException(status_code=422, detail='Invalid performance observation') from error


class PostQueueRequest(StrictModel):
    clip_id: str
    platform: Literal['youtube', 'instagram', 'tiktok']
    scheduled_at: datetime
    caption: str = Field(default='', max_length=5000)
    hashtags: list[str] = Field(default_factory=list, max_length=20)
    cta: Literal['follow', 'comment', 'save', 'share', 'profile', 'none'] = 'none'
    account_id: str | None = Field(default=None, max_length=200)

    @field_validator('scheduled_at', mode='before')
    @classmethod
    def parse_scheduled_at(cls, value):
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError as error:
                raise ValueError('scheduled_at must be an ISO 8601 datetime') from error
        return value


@router.post('/queue', response_model=PostQueueEntry, status_code=201)
def enqueue_post(body: PostQueueRequest, repository: Store = Depends(store)):
    try:
        record = body.model_dump(mode='json') | {'id': uuid.uuid4().hex}
        return repository.enqueue_post(record)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get('/queue', response_model=list[PostQueueEntry])
def post_queue(status: str | None = None, platform: str | None = None,
               repository: Store = Depends(store)):
    try:
        return repository.list_post_queue(status=status, platform=platform)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get('/posting-time/{platform}')
def posting_time(platform: Literal['youtube', 'instagram', 'tiktok'],
                 account_id: str | None = None,
                 repository: Store = Depends(store)):
    settings = load_settings()
    result = PostingTimeOptimizer(settings.posting.minimum_history_samples).recommend(
        platform, repository.posting_history(platform, account_id), timezone_name=settings.posting.timezone,
        default_windows=settings.posting.default_windows)
    return result
