"""One validated non-secret configuration source with explicit env precedence."""

import copy
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.errors import PipelineError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Clips(StrictModel):
    target_count: int = Field(ge=1, le=10000)
    min_duration: int = Field(ge=1, le=60)
    max_duration: int = Field(ge=1, le=180)
    target_duration: int = Field(ge=1, le=180)

    @model_validator(mode='after')
    def bounds(self):
        if not self.min_duration <= self.target_duration <= self.max_duration:
            raise ValueError('Invalid clip duration bounds')
        return self


class Captions(StrictModel):
    style: Literal['studio', 'colorized', 'pro', 'classic']
    words_per_line: int = Field(default=6, ge=1, le=10)
    max_lines: int = Field(default=2, ge=1, le=3)
    highlight_active_word: bool = True
    remove_fillers: bool = True


class Production(StrictModel):
    caption_style: Literal['studio', 'colorized', 'pro', 'classic']
    clips_per_source: int = Field(ge=1, le=20)


class Video(StrictModel):
    framing: Literal['fit', 'crop']
    width: Literal[1080]
    height: Literal[1920]
    encoder_profile: Literal['fast', 'balanced', 'max_quality']


class Selection(StrictModel):
    minimum_score: float = Field(ge=0, le=1)
    weights: dict[str, float]
    editorial: dict[str, float]

    @model_validator(mode='after')
    def weights_valid(self):
        names = {'hook', 'semantic', 'replay', 'emotion', 'completeness', 'velocity', 'engagement', 'standalone'}
        if (set(self.weights) != names or any(value < 0 for value in self.weights.values())
                or not math.isclose(sum(self.weights.values()), 1, abs_tol=1e-8)):
            raise ValueError('Selection weights must be normalized and use documented signals')
        coefficients = {'baseline', 'filler_penalty', 'question_bonus', 'referential_penalty',
            'mid_sentence_penalty', 'concrete_bonus', 'topic_bonus', 'topic_extra',
            'topic_extra_cap', 'opening_topic_bonus', 'opening_topic_cap', 'promotion_penalty',
            'completed_bonus', 'question_ending_penalty', 'silence_penalty', 'silence_cap',
            'linked_penalty', 'duration_penalty', 'duration_cap'}
        if set(self.editorial) != coefficients or any(not 0 <= value <= 100 for value in self.editorial.values()):
            raise ValueError('Editorial coefficients must use documented keys and finite nonnegative values')
        return self


class Dedup(StrictModel):
    timestamp_overlap_threshold: float = Field(gt=0, le=1)
    transcript_similarity_threshold: float = Field(gt=0, le=1)
    semantic_similarity_threshold: float = Field(gt=0, le=1)
    quote_words: int = Field(ge=4, le=100)


class Silence(StrictModel):
    threshold_db: int = Field(ge=-60, le=-10)
    min_duration_ms: int = Field(ge=50, le=5000)
    aggressive_cut: bool


class SourceFiltering(StrictModel):
    enabled: bool = True
    minimum_score: float = Field(default=0.55, ge=0, le=1)
    minimum_coverage: float = Field(default=0.35, ge=0, le=1)
    min_duration_minutes: int = Field(default=15, ge=1, le=1440)
    max_duration_hours: int = Field(default=8, ge=1, le=24)
    freshness_window_days: int = Field(default=14, ge=1, le=365)
    weights: dict[str, float]

    @model_validator(mode='after')
    def valid_weights(self):
        signals = {'velocity', 'relevance', 'freshness', 'engagement', 'channel_quality',
                   'transcript_available', 'replay_available', 'total_views', 'duration'}
        if (set(self.weights) != signals or any(value < 0 for value in self.weights.values())
                or not math.isclose(sum(self.weights.values()), 1, abs_tol=1e-8)):
            raise ValueError('Source-filter weights must be normalized and use documented signals')
        return self


class GrowthScoring(StrictModel):
    """PRD-GROWTH section 4 weights; normalized so missing evidence can renormalize."""

    hook_strength: float = Field(ge=0, le=1)
    retention_potential: float = Field(ge=0, le=1)
    shareability: float = Field(ge=0, le=1)
    standalone_clarity: float = Field(ge=0, le=1)
    emotional_intensity: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    niche_relevance: float = Field(ge=0, le=1)
    follow_potential: float = Field(ge=0, le=1)

    @model_validator(mode='after')
    def weights_valid(self):
        if not math.isclose(sum(self.model_dump().values()), 1, abs_tol=1e-8):
            raise ValueError('Growth scoring weights must be normalized')
        return self


class Hashtags(StrictModel):
    min: int = Field(default=3, ge=1, le=20)
    preferred: int = Field(default=5, ge=1, le=20)
    max: int = Field(default=8, ge=1, le=20)


class Posting(StrictModel):
    enabled: bool = False
    max_per_day: int = Field(default=3, ge=1, le=30)
    minimum_gap_minutes: int = Field(default=180, ge=1)
    default_windows: list[str] = Field(default_factory=lambda: ["12:00-14:00", "18:00-22:00"])
    timezone: str = 'Africa/Casablanca'
    same_source_hours: int = Field(default=8, ge=0, le=720)
    same_topic_hours: int = Field(default=6, ge=0, le=720)
    minimum_history_samples: int = Field(default=5, ge=1, le=10000)

    @model_validator(mode='after')
    def valid_calendar(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError('Posting timezone must be a valid IANA timezone') from error
        if not self.default_windows:
            raise ValueError('At least one fallback posting window is required')
        for value in self.default_windows:
            try:
                start, end = value.split('-', 1)
                if len(start) != 5 or len(end) != 5 or start >= end:
                    raise ValueError
                from datetime import time
                time.fromisoformat(start)
                time.fromisoformat(end)
            except (AttributeError, TypeError, ValueError) as error:
                raise ValueError('Posting windows must use increasing HH:MM-HH:MM values') from error
        return self


class CTA(StrictModel):
    categories: list[str] = Field(default_factory=lambda: ["follow", "comment", "save", "share", "profile", "none"])
    default_category: str = Field(default="none")
    exploration_ratio: float = Field(default=0.2, ge=0, le=1)


class Quality(StrictModel):
    minimum_score: float = Field(gt=0, le=1)
    minimum_speech_ratio: float = Field(ge=0, le=1)
    maximum_speech_gap: float = Field(ge=0, le=60)
    maximum_black_seconds: float = Field(gt=0, le=10)
    maximum_silence_ratio: float = Field(ge=0, le=1)
    minimum_audio_db: float = Field(ge=-100, le=0)
    minimum_fps: float = Field(gt=0, le=120)
    maximum_fps: float = Field(gt=0, le=240)
    maximum_subtitle_chars: int = Field(ge=8, le=100)
    duration_tolerance: float = Field(gt=0, le=2)


class Worker(StrictModel):
    concurrency: int = Field(ge=1, le=4)
    render_concurrency: int = Field(ge=1, le=4)
    download_concurrency: int = Field(ge=1, le=4)
    cpu_threads: int = Field(ge=1, le=16)
    memory_limit_mb: int = Field(ge=256, le=32768)
    maximum_attempts: int = Field(ge=1, le=10)
    retry_base_seconds: int = Field(ge=0, le=300)


class Whisper(StrictModel):
    model: str = Field(min_length=1, max_length=1000)
    device: Literal['cpu', 'cuda', 'auto']


class Paths(StrictModel):
    storage: str = Field(min_length=1)
    database: str = Field(min_length=1)
    output: str = Field(min_length=1)


class Publishing(StrictModel):
    enabled: Literal[False]


class Feedback(StrictModel):
    minimum_samples: int = Field(ge=2, le=10000)
    maximum_adjustment: float = Field(ge=0, le=0.25)


class DiscoveryEligibility(StrictModel):
    """One relaxation level of the source rules."""

    min_duration_minutes: int = Field(ge=1, le=1440)
    min_views: int = Field(ge=0, le=10_000_000_000)
    max_age_days: int = Field(ge=1, le=3650)
    min_score: float = Field(ge=0, le=1)
    require_views: bool = True
    require_age: bool = True


class DiscoveryProviders(StrictModel):
    youtube_api: bool = True
    yt_dlp: bool = True
    selenium: bool = True
    public_search: bool = True


class Discovery(StrictModel):
    """Discovery reliability, fallback and ranking settings."""

    mode: Literal['fast', 'balanced', 'deep'] = 'balanced'
    providers: DiscoveryProviders
    queries_per_niche: int = Field(ge=1, le=50)
    results_per_query: int = Field(ge=1, le=50)
    target_sources: int = Field(ge=1, le=50)
    minimum_sources: int = Field(ge=1, le=50)
    max_parallel_queries: int = Field(ge=1, le=16)
    provider_timeout_seconds: int = Field(ge=1, le=600)
    total_timeout_seconds: int = Field(ge=1, le=3600)
    cache_ttl_hours: int = Field(ge=0, le=168)
    language: str = Field(min_length=2, max_length=16)
    region: str = Field(min_length=2, max_length=16)
    whitelist_boost: float = Field(ge=0, le=0.5)
    freshness_window_days: int = Field(ge=1, le=365)
    secondary_lookup_limit: int = Field(ge=0, le=50)
    families: list[str]
    eligibility: dict[str, DiscoveryEligibility]
    scoring_weights: dict[str, float]

    @model_validator(mode='after')
    def valid_discovery(self):
        if set(self.eligibility) != {'strict', 'medium', 'relaxed'}:
            raise ValueError('Discovery eligibility needs strict, medium and relaxed tiers')
        if self.minimum_sources > self.target_sources:
            raise ValueError('Discovery minimum sources cannot exceed the target')
        if not self.families or any(not isinstance(item, str) or not item.strip() for item in self.families):
            raise ValueError('Discovery query families must be nonempty strings')
        signals = {'velocity', 'relevance', 'engagement', 'freshness', 'channel_quality',
                   'transcript_signal'}
        if (set(self.scoring_weights) != signals or any(value < 0 for value in self.scoring_weights.values())
                or not math.isclose(sum(self.scoring_weights.values()), 1, abs_tol=1e-8)):
            raise ValueError('Discovery scoring weights must be normalized and use documented signals')
        return self


class Settings(StrictModel):
    clips: Clips
    captions: Captions
    production: Production
    video: Video
    selection: Selection
    dedup: Dedup
    source_filter: SourceFiltering
    growth_scoring: GrowthScoring
    quality: Quality
    worker: Worker
    whisper: Whisper
    paths: Paths
    publishing: Publishing
    posting: Posting
    cta: CTA
    hashtags: Hashtags
    silence: Silence
    feedback: Feedback
    discovery: Discovery


def merge(base, override):
    if not isinstance(override, dict):
        raise ValueError('Configuration must be a mapping')
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else value
    return result


@lru_cache(maxsize=16)
def read_yaml(path, modified):
    path = Path(path)
    if path.stat().st_size > 128_000:
        raise ValueError('Configuration exceeds size limit')
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}


def load_settings(*, overlay=None, profile=None, environ=None):
    env = os.environ if environ is None else environ
    folder = Path(__file__).resolve().parents[2] / 'config'
    profile = profile or env.get('CONTENT_REWARD_PROFILE', 'development')
    try:
        if profile not in ('development', 'production'):
            raise ValueError('Unknown configuration profile')
        data = {}
        for path in [folder / 'default.yaml', folder / f'{profile}.yaml'] + ([Path(overlay or env['CONTENT_REWARD_CONFIG'])] if overlay or env.get('CONTENT_REWARD_CONFIG') else []):
            data = merge(data, read_yaml(str(path.resolve()), path.stat().st_mtime_ns))
        overrides = {
            'CLIPPING_TARGET_COUNT': ('clips', 'target_count', int),
            'CLIPPING_STORAGE': ('paths', 'storage', str),
            'CLIPPING_DATABASE': ('paths', 'database', str),
            'CLIPPING_OUTPUT': ('paths', 'output', str),
            'WHISPER_MODEL': ('whisper', 'model', str),
            'WHISPER_DEVICE': ('whisper', 'device', str),
            'CLIPPING_CPU_THREADS': ('worker', 'cpu_threads', int),
            'CLIPPING_MAXIMUM_ATTEMPTS': ('worker', 'maximum_attempts', int),
        }
        for name, (section, key, convert) in overrides.items():
            if env.get(name):
                data[section][key] = convert(env[name])
        return Settings.model_validate(data)
    except (OSError, ValueError, TypeError, ValidationError, yaml.YAMLError):
        raise PipelineError('CONFIG_ERROR') from None
