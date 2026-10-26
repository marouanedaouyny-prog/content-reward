"""The bridge between the discovery engine and the clipping pipeline.

The pipeline consumes normalized source records only. It never needs to know
which provider found a video, and discovery never downloads media: only
metadata is collected here, before any clip window is chosen.
"""

from datetime import datetime, timezone

from clipping.discovery.models import SourceCandidate


def niche_name(niche):
    """The display name of a search niche."""
    if isinstance(niche, dict):
        return str(niche.get('name') or '')
    return str(niche or '')


def source_record(candidate, niche, *, score=None, tier=None, observed_at=None):
    """Convert one normalized candidate into the pipeline's source record.

    The record keeps the fields the clipping pipeline already consumes. A
    source is only eligible when its publication date, view count and duration
    are all observed, because the pipeline needs all three before it can
    select a clip window.
    """
    from clipping import trends
    published = candidate.upload_date
    duration = candidate.duration_seconds
    velocity = candidate.views_per_hour
    name = niche_name(niche)
    return {
        'id': candidate.id,
        'url': candidate.url,
        'title': candidate.title,
        'creator': candidate.channel or 'Unknown creator',
        'niches': [name] if name else [],
        'views': candidate.views,
        'published_at': published.isoformat() if published else None,
        'observed_at': observed_at or datetime.now(timezone.utc).isoformat(),
        'duration': duration,
        'views_per_hour_since_upload': round(velocity, 2) if velocity is not None else None,
        'measured_growth_per_hour': None,
        'eligible_preview': bool(published is not None and candidate.views is not None
                                 and duration is not None
                                 and trends.MIN_SOURCE_SECONDS < duration <= trends.MAX_SOURCE_SECONDS),
        'transcript_status': candidate.transcript_status,
        'providers_seen': list(candidate.providers_seen),
        'discovery_provider': candidate.provider,
        'source_score': score,
        'eligibility_tier': tier,
    }


def records_from(candidates, niche, *, scores=None, tier=None):
    """Convert a list of normalized candidates into pipeline source records."""
    scores = scores or {}
    return [source_record(candidate, niche, score=scores.get(candidate.id), tier=tier)
            for candidate in candidates]


def search_sources(niche, *, mode='balanced', use_cache=True, providers=None, settings=None,
                   storage=None):
    """Run one discovery and return the pipeline-ready source records."""
    from clipping.discovery import service
    outcome = service.discover(niche, storage=storage, mode=mode, use_cache=use_cache,
                               settings=settings, providers=providers)
    return records_from(outcome.sources, niche, tier=outcome.tier), outcome


def supplement(niches, *, mode='balanced', use_cache=True, settings=None, storage=None,
               limit=3, target=5):
    """Broaden discovery over several niches until enough sources are found.

    The engine runs one niche at a time so a single failing niche never ends
    the search, and the loop stops as soon as the requested number of sources
    is available.
    """
    records, outcomes = [], []
    for niche in list(niches or ())[:max(1, int(limit))]:
        found, outcome = search_sources(niche, mode=mode, use_cache=use_cache,
                                        settings=settings, storage=storage)
        records.extend(found)
        outcomes.append(outcome)
        if len(records) >= max(1, int(target)):
            break
    return records, outcomes


__all__ = ['SourceCandidate', 'niche_name', 'records_from', 'search_sources', 'source_record',
           'supplement']
