"""Process-local admission limits; configuration changes wait for idle resources."""

import threading
from contextlib import contextmanager

from app.core.errors import PipelineError

_condition = threading.Condition()
_resources = {}


@contextmanager
def resource_gate(name, capacity):
    if not isinstance(capacity, int) or isinstance(capacity, bool) or not 1 <= capacity <= 4:
        raise PipelineError('CONFIG_ERROR')
    with _condition:
        state = _resources.setdefault(name, {'capacity': capacity, 'active': 0})
        if state['capacity'] != capacity:
            if state['active']:
                raise PipelineError('CONFIG_ERROR')
            state['capacity'] = capacity
        while state['active'] >= capacity:
            from clipping.media import _stop_signal, ProcessingInterrupted
            stop = _stop_signal.get()
            if stop and stop():
                raise ProcessingInterrupted('Processing paused while waiting for resources')
            _condition.wait(.25)
        state['active'] += 1
    try:
        yield
    finally:
        with _condition:
            state['active'] -= 1
            _condition.notify_all()
