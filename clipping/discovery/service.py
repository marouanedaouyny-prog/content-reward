"""Discovery service.

The service assembles the engine with the real settings, cache and history so
the command line, the clipping pipeline and the tests all use one configured
instance. It never hides a provider failure and never contacts a social
account.
"""

from pathlib import Path

from clipping.discovery.cache import DiscoveryCache
from clipping.discovery.engine import DiscoveryEngine, DiscoveryOutcome
from clipping.discovery.health import ProviderHealth
from clipping.discovery.history import SourceHistory
from clipping.discovery.models import DiscoveryError

DEFAULT_STORAGE = Path(__file__).resolve().parents[2] / 'storage' / 'clipping'


def _settings():
    from app.core.config import load_settings
    return load_settings()


def database_path(storage=None):
    folder = Path(storage or DEFAULT_STORAGE).resolve()
    return folder / 'content-reward.db'


def build_engine(storage=None, *, settings=None, event=None, providers=None):
    """Create a configured discovery engine with a bounded cache and source history."""
    settings = settings or _settings()
    path = database_path(storage)
    path.parent.mkdir(parents=True, exist_ok=True)
    from app.repositories.cache import CacheRepository
    discovery = getattr(settings, 'discovery', None)
    ttl_hours = int(getattr(discovery, 'cache_ttl_hours', 3) or 0)
    cache = DiscoveryCache(repository=CacheRepository(path), ttl_hours=ttl_hours)
    history = SourceHistory(path)
    return DiscoveryEngine(settings=settings, providers=providers, cache=cache,
                           health=ProviderHealth(), history=history, event=event)


def discover(niche, *, storage=None, mode='balanced', region=None, language=None,
             use_cache=True, dry_run=False, debug=False, settings=None, providers=None):
    """Run one discovery and return its outcome, including any structured error."""
    engine = build_engine(storage, settings=settings, providers=providers)
    outcome = engine.discover(niche, mode=mode, region=region, language=language,
                               use_cache=use_cache, dry_run=dry_run, debug=debug)
    return outcome


def health(storage=None, settings=None):
    """Report the observed health of the discovery providers."""
    engine = build_engine(storage, settings=settings)
    return {'providers': engine.health.report(),
            'cache': engine.cache.stats(),
            'note': 'Provider health is observed in this process. A provider that never ran is unknown, '
                    'not failed.'}


def source_history(storage=None, limit=100):
    """Report the sources this project has considered before."""
    path = database_path(storage)
    path.parent.mkdir(parents=True, exist_ok=True)
    history = SourceHistory(path)
    return {'sources': history.report()[:limit],
            'queries': history.query_performance(),
            'blacklist': sorted(history.blacklist_ids())}


__all__ = ['DiscoveryError', 'DiscoveryOutcome', 'build_engine', 'database_path', 'discover',
           'health', 'source_history']
