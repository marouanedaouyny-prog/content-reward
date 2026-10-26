"""Bounded cache for discovery search results.

Repeated searches of the same query waste network time and can trigger public
rate limits. The cache key includes the query, the provider, the region, the
language and a hash of the active configuration, so a changed rule never
reuses a stale result.
"""

import hashlib
import json

KIND = 'discovery_search_results'


def config_hash(value):
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str,
                             allow_nan=False).encode('utf-8')
    except (TypeError, ValueError):
        return 'unhashable'
    return hashlib.sha256(encoded).hexdigest()[:16]


class DiscoveryCache:
    """Cache provider results per query, provider and search context."""

    def __init__(self, repository=None, ttl_hours=3, enabled=True):
        self.repository = repository
        self.ttl_hours = max(0, int(ttl_hours))
        self.enabled = bool(enabled) and repository is not None and self.ttl_hours > 0
        self.hits = 0
        self.misses = 0

    def identity(self, query, provider, region, language, config=None):
        return {'query': query, 'provider': provider, 'region': region, 'language': language,
                'config': config_hash(config)}

    def get(self, query, provider, region, language, config=None):
        if not self.enabled:
            self.misses += 1
            return None
        value = self.repository.get_json(KIND, self.identity(query, provider, region, language, config),
                                         max_bytes=4_000_000)
        if not isinstance(value, list):
            self.misses += 1
            return None
        self.hits += 1
        return value

    def put(self, query, provider, region, language, records, config=None):
        if not self.enabled or not isinstance(records, list):
            return False
        try:
            self.repository.put_json(KIND, self.identity(query, provider, region, language, config),
                                     records, ttl_seconds=self.ttl_hours * 3600, max_bytes=4_000_000)
        except ValueError:
            return False
        return True

    def stats(self):
        return {'enabled': self.enabled, 'ttl_hours': self.ttl_hours,
                'hits': self.hits, 'misses': self.misses}
