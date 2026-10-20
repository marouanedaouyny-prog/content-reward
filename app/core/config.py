"""One validated non-secret configuration source with explicit env precedence."""

import copy
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

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


class Production(StrictModel):
    caption_style: Literal['studio', 'colorized', 'pro', 'classic']
    clips_per_source: int = Field(ge=1, le=20)


class Video(StrictModel):
    framing: Literal['fit', 'crop']
    width: Literal[1080]
    height: Literal[1920]


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


class Quality(StrictModel):
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
    concurrency: Literal[1]
    render_concurrency: Literal[1]
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


class Settings(StrictModel):
    clips: Clips
    captions: Captions
    production: Production
    video: Video
    selection: Selection
    dedup: Dedup
    quality: Quality
    worker: Worker
    whisper: Whisper
    paths: Paths
    publishing: Publishing
    feedback: Feedback


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
