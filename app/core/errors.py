"""Public errors never include provider exception text or credentials."""

MESSAGES = {
    'NETWORK_ERROR': 'Network request failed.',
    'SOURCE_UNAVAILABLE': 'Public source is unavailable.',
    'DOWNLOAD_ERROR': 'Selected source download failed.',
    'TRANSCRIPTION_ERROR': 'Speech transcription needs review.',
    'RENDER_ERROR': 'Clip rendering failed.',
    'VALIDATION_ERROR': 'Content or artifact validation failed.',
    'PUBLISH_ERROR': 'Publication could not be completed.',
    'RATE_LIMIT': 'Provider rate limit reached.',
    'AUTH_ERROR': 'Account access is unavailable.',
    'CONFIG_ERROR': 'Configuration is invalid; check documented keys and ranges.',
}
RETRYABLE = {'NETWORK_ERROR', 'SOURCE_UNAVAILABLE', 'RATE_LIMIT'}


class PipelineError(Exception):
    def __init__(self, code, *, stage='configuration', retryable=None):
        if code not in MESSAGES:
            raise ValueError('Unknown pipeline error code')
        self.code, self.stage = code, stage
        self.retryable = code in RETRYABLE if retryable is None else bool(retryable)
        super().__init__(MESSAGES[code])

    def as_dict(self):
        return dict(code=self.code, stage=self.stage, retryable=self.retryable, message=str(self))


def retry_delay(failed_attempts, *, maximum_attempts, base=5, maximum_delay=300):
    if (isinstance(failed_attempts, bool) or not isinstance(failed_attempts, int)
            or not 1 <= failed_attempts or not 1 <= maximum_attempts <= 10
            or not 0 <= base <= maximum_delay <= 3600):
        raise ValueError('Invalid retry policy')
    return min(maximum_delay, base * 2 ** (failed_attempts - 1)) if failed_attempts < maximum_attempts else None
