import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.core.config import StrictModel

Platform = Literal['youtube', 'tiktok', 'instagram']


def platform_name(value):
    return 'youtube' if value == 'youtube_shorts' else value


class Rules(StrictModel):
    min_duration: float = Field(default=15, ge=1, le=180)
    max_duration: float = Field(default=60, ge=1, le=180)
    allowed_platforms: list[Platform] = Field(default_factory=lambda: ['youtube', 'tiktok', 'instagram'])
    required_hashtags: list[str] = Field(default_factory=list)
    forbidden_topics: list[str] = Field(default_factory=list)
    minimum_views: int = Field(default=0, ge=0)
    allowed_source_ids: list[str] = Field(default_factory=list)
    required_creator: str | None = None

    @field_validator('allowed_platforms', mode='before')
    @classmethod
    def platforms(cls, values):
        return [platform_name(value) for value in values] if isinstance(values, list) else values

    @model_validator(mode='after')
    def validate_rules(self):
        if self.min_duration > self.max_duration or not self.allowed_platforms:
            raise ValueError('Campaign needs valid duration bounds and destinations')
        if any(not tag.startswith('#') or len(tag.split()) != 1 for tag in self.required_hashtags):
            raise ValueError('Required hashtags must start with # and contain no spaces')
        if any(not topic.strip() for topic in self.forbidden_topics):
            raise ValueError('Forbidden topics cannot be empty')
        return self


class Campaign(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform
    title: str = Field(min_length=1, max_length=300)
    creator: str | None = None
    rules: Rules = Field(default_factory=Rules)
    rules_reviewed: bool = False
    rights_confirmed: bool = False
    payout_model: dict = Field(default_factory=dict)
    deadline: datetime | None = Field(default=None, strict=False)
    status: Literal['draft', 'active', 'closed'] = 'draft'

    @field_validator('deadline')
    @classmethod
    def aware_deadline(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('Campaign deadline must include a timezone')
        return value
