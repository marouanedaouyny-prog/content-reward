from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator

from app.core.config import StrictModel
from app.repositories.database import timestamp


class MeasurementContext(StrictModel):
    """Non-secret scope and denominator semantics for comparable observations."""
    account_id: str | None = Field(default=None, min_length=1, max_length=200)
    reporting_window_hours: float | None = Field(default=None, gt=0)
    view_definition: Literal['unknown', 'play_starts', 'engaged_views', 'qualified_views',
                             'platform_reported'] = 'unknown'
    definition_version: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator('account_id', 'definition_version')
    @classmethod
    def bounded_identifier(cls, value):
        if value is not None and (not value.strip() or value != value.strip()
                                  or any(char in value for char in '\r\n\t')):
            raise ValueError('Measurement identifiers must be nonempty single-line values')
        return value

    @property
    def cohort_key(self):
        if self.account_id is None or self.reporting_window_hours is None or self.view_definition == 'unknown':
            return None
        return (self.account_id, self.reporting_window_hours, self.view_definition, self.definition_version)


class ClipPerformance(StrictModel):
    clip_id: str
    platform: Literal['youtube', 'instagram', 'tiktok']
    collected_at: str = Field(default_factory=timestamp)
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    profile_visits: int | None = Field(default=None, ge=0)
    average_watch_time: float | None = Field(default=None, ge=0)
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    retention: float | None = Field(default=None, ge=0, le=1)
    average_view_percentage: float | None = Field(default=None, ge=0)
    audience_watch_ratio: float | None = Field(default=None, ge=0)
    measurement_context: MeasurementContext | None = None
    followers_generated: int | None = Field(default=None, ge=0,
        validation_alias=AliasChoices('followers_generated', 'followers_gained'))
    hashtags: list[str] | None = Field(default=None, max_length=20)
    cta_used: Literal['follow', 'comment', 'save', 'share', 'profile', 'none'] | None = None
    campaign_accepted: bool | None = None
    campaign_rejected: bool | None = None
    rejection_reason: str | None = None
    reward_amount: Decimal | None = None
    provenance: Literal['manual', 'imported_export'] = 'manual'

    @field_validator('collected_at')
    @classmethod
    def aware_time(cls, value):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('Metrics need a collection timezone')
        return parsed.astimezone(timezone.utc).isoformat()

    @field_validator('reward_amount', mode='before')
    @classmethod
    def finite_money(cls, value):
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError('Reward observations must be valid finite amounts') from error
        if not amount.is_finite() or amount < 0:
            raise ValueError('Reward observations must be finite and nonnegative')
        return amount

    @field_validator('hashtags')
    @classmethod
    def valid_observed_hashtags(cls, values):
        if values is None:
            return None
        if any(not value.startswith('#') or len(value) < 2 or any(char.isspace() for char in value)
               for value in values):
            raise ValueError('Observed hashtags must be single words beginning with #')
        return list(dict.fromkeys(values))

    @model_validator(mode='after')
    def decision(self):
        if self.campaign_accepted and self.campaign_rejected:
            raise ValueError('A campaign observation cannot be accepted and rejected together')
        return self
