"""Structured, credential-redacted events suitable for JSONL and SQLite."""

import json
import logging
import re
from datetime import datetime, timezone

SENSITIVE = re.compile(r'(?i)(secret|password|passwd|token|cookie|authorization|api.?key)')


def redact(value):
    if isinstance(value, dict):
        return {str(key): '[REDACTED]' if SENSITIVE.search(str(key)) else redact(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)(https?://)[^/\s@]+@', r'\1[REDACTED]@', value)
        value = re.sub(r'(?i)((?:[\w-]*(?:token|secret|password|cookie|api[_-]?key)[\w-]*)[=:]\s*)[^&\s,;]+',
                       r'\1[REDACTED]', value)
        value = re.sub(r'(?i)Bearer\s+\S+', 'Bearer [REDACTED]', value)
    return value


def event_record(event, *, level='INFO', order_id=None, clip_id=None, stage=None,
                 duration_ms=None, error_code=None, message='', **fields):
    return redact(dict(timestamp=datetime.now(timezone.utc).isoformat(), level=level,
                       order_id=order_id, clip_id=clip_id, stage=stage, event=event,
                       duration_ms=duration_ms, error_code=error_code, message=message, **fields))


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(event_record(getattr(record, 'event', 'log'), level=record.levelname,
                                       message=record.getMessage(),
                                       stage=getattr(record, 'stage', None)), ensure_ascii=True)
