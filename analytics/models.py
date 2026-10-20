from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.core.config import StrictModel
from app.repositories.database import timestamp


class ClipPerformance(StrictModel):
    clip_id: str
    platform: Literal['youtube', 'instagram', 'tiktok']
    collected_at: str = Field(default_factory=timestamp)
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    average_watch_time: float | None = Field(default=None, ge=0)
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    retention: float | None = Field(default=None, ge=0, le=1)
    followers_generated: int | None = Field(default=None, ge=0)
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
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError('Reward observations must be finite and nonnegative')
        return amount

    @model_validator(mode='after')
    def decision(self):
        if self.campaign_accepted and self.campaign_rejected:
            raise ValueError('A campaign observation cannot be accepted and rejected together')
        return self
