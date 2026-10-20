import json

import pytest


def test_transitions_reject_skipped_or_terminal_work():
    from app.core.state import transition
    assert transition('CREATED', 'DISCOVERING') == 'DISCOVERING'
    assert transition('FAILED', 'RENDERING', resume=True) == 'RENDERING'
    with pytest.raises(ValueError):
        transition('CREATED', 'PUBLISHED')
    with pytest.raises(ValueError):
        transition('COMPLETED', 'DOWNLOADING', resume=True)


def test_retry_policy_is_finite_and_errors_have_safe_defaults():
    from app.core.errors import PipelineError, retry_delay
    error = PipelineError('AUTH_ERROR', stage='publish')
    assert not error.retryable
    assert retry_delay(1, maximum_attempts=3, base=5) == 5
    assert retry_delay(2, maximum_attempts=3, base=5) == 10
    assert retry_delay(3, maximum_attempts=3, base=5) is None


def test_events_redact_credentials_in_nested_fields():
    from app.core.logging import event_record
    record = event_record('render_completed', order_id='order', stage='render',
                          message='token=private-value https://user:pass@example.com/?access_token=hidden',
                          context={'client_secret': 'never-print', 'count': 2})
    assert {'timestamp', 'level', 'clip_id', 'duration_ms', 'error_code'} <= record.keys()
    rendered = json.dumps(record)
    assert all(value not in rendered for value in ['private-value', 'user:pass', 'hidden', 'never-print'])
    assert record['context']['count'] == 2


@pytest.mark.parametrize('message', [
    '{"access_token": "dummy-private-marker"}',
    "{'client_secret': 'dummy-private-marker'}",
    'Authorization: Basic dummy-private-marker',
])
def test_redaction_handles_quoted_and_basic_auth_forms(message):
    from app.core.logging import redact
    assert 'dummy-private-marker' not in redact(message)
