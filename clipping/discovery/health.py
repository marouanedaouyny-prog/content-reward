"""Provider health for discovery.

A provider that keeps failing should not be attempted first on every run. The
health tracker records success rate, recent failures, latency and result count,
and reorders the provider chain so healthy providers run first. A provider
that has never run is never penalized.
"""

from collections import deque


class ProviderHealth:
    """Track provider outcomes and rank the chain by observed reliability."""

    def __init__(self, window=10, minimum_success_rate=0.25, deprioritized_failures=3):
        self.window = max(1, int(window))
        self.minimum_success_rate = float(minimum_success_rate)
        self.deprioritized_failures = max(1, int(deprioritized_failures))
        self.records = {}

    def _entry(self, provider):
        return self.records.setdefault(provider, {'successes': 0, 'failures': 0, 'results': 0,
                                                  'latencies': deque(maxlen=self.window),
                                                  'errors': deque(maxlen=self.window)})

    def record_success(self, provider, results=0, duration_ms=0):
        entry = self._entry(provider)
        entry['successes'] += 1
        entry['results'] += max(0, int(results))
        entry['latencies'].append(max(0, int(duration_ms)))
        return entry

    def record_failure(self, provider, error_code='PROVIDER_FAILED', duration_ms=0):
        entry = self._entry(provider)
        entry['failures'] += 1
        entry['latencies'].append(max(0, int(duration_ms)))
        entry['errors'].append(str(error_code))
        return entry

    def status(self, provider):
        entry = self.records.get(provider)
        if not entry:
            return {'provider': provider, 'attempts': 0, 'success_rate': None,
                    'recent_failures': 0, 'average_latency_ms': None, 'results': 0,
                    'deprioritized': False}
        attempts = entry['successes'] + entry['failures']
        recent = list(entry['errors'])[-self.deprioritized_failures:]
        deprioritized = len(recent) >= self.deprioritized_failures
        latency = list(entry['latencies'])
        return {'provider': provider, 'attempts': attempts,
                'success_rate': (entry['successes'] / attempts) if attempts else None,
                'recent_failures': len(recent), 'average_latency_ms': (
                    round(sum(latency) / len(latency), 1) if latency else None),
                'results': entry['results'], 'deprioritized': deprioritized,
                'last_error': entry['errors'][-1] if entry['errors'] else None}

    def report(self):
        return [self.status(name) for name in sorted(self.records)]

    def order(self, providers):
        """Return the providers ordered by observed health, keeping the given order for unknowns."""
        healthy, unknown, broken = [], [], []
        for name in providers:
            entry = self.records.get(name)
            if not entry:
                unknown.append(name)
                continue
            attempts = entry['successes'] + entry['failures']
            recent = list(entry['errors'])[-self.deprioritized_failures:]
            if len(recent) >= self.deprioritized_failures:
                broken.append(name)
            elif attempts and entry['successes'] / attempts < self.minimum_success_rate:
                broken.append(name)
            else:
                healthy.append(name)
        return healthy + unknown + broken
