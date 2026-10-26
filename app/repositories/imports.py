"""Validate historical JSON at its one-time import boundary."""

import math
from dataclasses import asdict


def validate_order_snapshot(state, identifier):
    # Use the same settings validation as resume; imports must not turn invalid
    # historical configuration into authoritative database records.
    from clipping.orchestrator import Config
    if not isinstance(state, dict) or state.get('id') != identifier or not isinstance(state.get('config'), dict):
        raise ValueError('Historical manifest identity or configuration mismatch')
    config = Config(**state['config'])
    config.validate()
    state['config'] = asdict(config)
    for field in ('status', 'stage', 'created_at'):
        if not isinstance(state.get(field), str) or not 1 <= len(state[field]) <= 100:
            raise ValueError('Invalid historical order field')
    count = state.setdefault('connection_failures', 0)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError('Invalid historical retry count')
    for field in ('clip_entries', 'skipped_entries', 'moments'):
        entries = state.get(field, [])
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError('Invalid historical candidate collection')
    source = state.get('source_selection')
    if source is not None and not isinstance(source, dict):
        raise ValueError('Invalid historical source')
    moments = state.get('moments', [])
    for index, entry in enumerate(state.get('clip_entries', []) + state.get('skipped_entries', [])):
        moment = entry.get('moment') or (moments[index] if index < len(moments) else {})
        source = entry.get('source') or state.get('source_selection') or {}
        if not isinstance(moment, dict) or not isinstance(source, dict):
            raise ValueError('Invalid historical candidate')
        plan = entry.get('source_clip_plan') or moment.get('clip_plan')
        if not plan:
            continue
        if not isinstance(plan, dict):
            raise ValueError('Invalid historical source window')
        for name in ('start_seconds', 'duration_seconds'):
            value = plan.get(name)
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                    or value < 0 or name == 'duration_seconds' and value == 0):
                raise ValueError('Invalid historical source window')
    return state
