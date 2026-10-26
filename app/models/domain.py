from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OrderSummary(BaseModel):
    id: str
    status: str
    stage: str
    requested_clip_count: int
    completed_clip_count: int
    reason: str | None = None

    @classmethod
    def from_state(cls, state):
        return cls(id=state['id'], status=state['status'], stage=state['stage'],
                   requested_clip_count=state['config']['clip_count'],
                   completed_clip_count=state.get('completed_clip_count', 0), reason=state.get('reason'))


class ClipSummary(BaseModel):
    id: str
    order_id: str
    path: str
    subtitles: str | None
    sha256: str
    caption: str
    caption_style: str
    framing: str
    status: str
    available: bool | None = None
    missing_artifacts: list[str] = Field(default_factory=list)
    changed_artifacts: list[str] = Field(default_factory=list)
    integrity: str | None = None


class PerformancePeriod(BaseModel):
    period_start: str
    observations: int
    measured_clips: int
    views_samples: int
    views: int | None
    followers_samples: int
    followers_generated: int | None
    follower_conversion_samples: int
    followers_per_1000_views: float | None
    profile_visits_samples: int
    profile_visits: int | None
    completion_rate_samples: int
    completion_rate_mean: float | None
    average_watch_time_samples: int
    average_watch_time_mean: float | None


class MetricsSummary(BaseModel):
    clips_generated: int
    clips_generated_per_day: float
    reporting_window_days: int
    measured_clips: int
    views_per_clip: float | None
    profile_visits: int | None
    follow_conversion_samples: int
    follow_conversion_rate: float | None
    followers_per_1000_views: float | None
    followers_per_1000_views_by_clip: dict[str, float]
    successful_render_rate: float | None
    render_attempts: int
    prepared_publications: int
    publish_success_rate: float | None
    publication_attempts: int
    campaign_acceptance_rate: float | None
    campaign_decisions: int
    reward_per_clip: str | None
    reward_observations: int
    reward_by_source: dict[str, str]
    reward_by_niche: dict[str, str]
    reward_per_hour: float | None
    average_pipeline_duration_ms: float | None
    cache_requests: int
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float | None
    cache_bytes_reused: int
    cache_by_kind: dict[str, dict[str, int | float]]
    performance_periods: dict[Literal['daily', 'weekly', 'monthly'], list[PerformancePeriod]]
    limitations: list[str]


class PostQueueEntry(BaseModel):
    id: str
    clip_id: str
    platform: Literal['youtube', 'instagram', 'tiktok']
    scheduled_at: datetime
    caption: str = Field(max_length=5000)
    hashtags: list[str] = Field(default_factory=list, max_length=20)
    cta: Literal['follow', 'comment', 'save', 'share', 'profile', 'none'] = 'none'
    account_id: str | None = Field(default=None, max_length=200)
    status: Literal['READY', 'SCHEDULED'] = 'SCHEDULED'

    @field_validator('scheduled_at')
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Scheduled time must include a timezone')
        return value.astimezone(timezone.utc)

    @field_validator('hashtags')
    @classmethod
    def valid_hashtags(cls, values):
        if any(not isinstance(value, str) or not value.startswith('#') or len(value.split()) != 1
               for value in values):
            raise ValueError('Hashtags must be single words beginning with #')
        return list(dict.fromkeys(values))
