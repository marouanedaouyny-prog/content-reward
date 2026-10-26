"""Explicit bounded FFmpeg encoder tradeoffs; balanced preserves current output defaults."""

from app.core.errors import PipelineError

PROFILES = {
    'fast': {'preset': 'ultrafast', 'crf': 25},
    'balanced': {'preset': 'fast', 'crf': 23},
    'max_quality': {'preset': 'slow', 'crf': 20},
}


def encoder_options(profile):
    try:
        return dict(PROFILES[profile])
    except (KeyError, TypeError) as error:
        raise PipelineError('CONFIG_ERROR') from error
