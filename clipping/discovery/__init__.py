"""Resilient source discovery for the clipping pipeline.

The package holds one flow: broaden the search, normalize the results,
filter locally, relax progressively when needed, rank the survivors and report
exactly what happened.
"""

from clipping.discovery.cache import DiscoveryCache
from clipping.discovery.eligibility import DEFAULT_TIERS, EligibilityEngine, EligibilityTier
from clipping.discovery.engine import DiscoveryEngine, DiscoveryOutcome
from clipping.discovery.health import ProviderHealth
from clipping.discovery.history import SourceHistory
from clipping.discovery.models import (DiscoveryDiagnostics, DiscoveryError, ProviderStatus,
                                       QueryStatus, SourceCandidate)
from clipping.discovery.providers import (DiscoveryProvider, ProviderError, PublicSearchProvider,
                                           SeleniumProvider, YouTubeApiProvider, YtDlpProvider)
from clipping.discovery.queries import QueryGenerator
from clipping.discovery.scoring import SourceScorer

__all__ = [
    'DEFAULT_TIERS', 'DiscoveryCache', 'DiscoveryDiagnostics', 'DiscoveryEngine',
    'DiscoveryError', 'DiscoveryOutcome', 'DiscoveryProvider', 'EligibilityEngine',
    'EligibilityTier', 'ProviderError', 'ProviderHealth', 'ProviderStatus', 'PublicSearchProvider',
    'QueryGenerator', 'QueryStatus', 'SeleniumProvider', 'SourceCandidate', 'SourceHistory',
    'SourceScorer', 'YouTubeApiProvider', 'YtDlpProvider',
]
