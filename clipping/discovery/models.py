"""Normalized discovery records shared by every provider and the clip pipeline.

A provider only searches. It never decides whether a video is usable. Every
provider result is normalized into a `SourceCandidate` so the eligibility
engine, the scorer and the clipping pipeline see one shape and never need to
know which provider found a video.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
CANONICAL_URL = re.compile(r'^https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})$')
TRANSCRIPT_STATES = ('AVAILABLE', 'UNKNOWN', 'UNAVAILABLE')


def now():
    return datetime.now(timezone.utc)


def finite_number(value):
    """Return a finite nonnegative number, or None for missing or invalid metadata."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float('inf'), float('-inf')) and number >= 0 else None


def parse_datetime(value):
    """Parse the several public upload-date shapes without inventing a date."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if re.fullmatch(r'\d{8}', text):
            try:
                return datetime.strptime(text, '%Y%m%d').replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        try:
            parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


@dataclass
class SourceCandidate:
    """One discovered video, normalized and safe to merge across providers."""

    id: str
    title: str
    url: str
    duration_seconds: int | None = None
    views: int | None = None
    upload_date: datetime | None = None
    channel: str | None = None
    provider: str = 'unknown'
    channel_id: str | None = None
    description: str | None = None
    is_live: bool = False
    transcript_status: str = 'UNKNOWN'
    providers_seen: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.id, str) or not VIDEO_ID.fullmatch(self.id):
            raise ValueError('A source candidate needs a valid YouTube video identifier')
        if not isinstance(self.url, str) or not CANONICAL_URL.fullmatch(self.url):
            raise ValueError('A source candidate needs a canonical public watch URL')
        if self.transcript_status not in TRANSCRIPT_STATES:
            raise ValueError('Transcript availability must be AVAILABLE, UNKNOWN or UNAVAILABLE')
        if self.duration_seconds is not None:
            self.duration_seconds = int(self.duration_seconds)
        if self.views is not None:
            self.views = int(self.views)
        if not self.providers_seen:
            self.providers_seen = [self.provider]
        else:
            self.providers_seen = list(dict.fromkeys(self.providers_seen))
        self.metadata = dict(self.metadata or {})

    @property
    def age_hours(self):
        if self.upload_date is None:
            return None
        return max((now() - self.upload_date).total_seconds() / 3600, 0.0)

    @property
    def views_per_hour(self):
        """Lifetime views per hour, protected against a tiny sample of a brand new video."""
        if self.views is None or self.upload_date is None:
            return None
        age = max((now() - self.upload_date).total_seconds() / 3600, 1.0)
        return self.views / age

    def merge(self, other):
        """Keep the richer observation of the same video and remember both providers."""
        if not isinstance(other, SourceCandidate) or other.id != self.id:
            raise ValueError('Only the same video can be merged')
        if other.duration_seconds is not None and self.duration_seconds is None:
            self.duration_seconds = other.duration_seconds
        if other.views is not None and self.views is None:
            self.views = other.views
        if self.upload_date is None:
            self.upload_date = other.upload_date
        if not self.channel:
            self.channel = other.channel
        if not self.channel_id:
            self.channel_id = other.channel_id
        if not self.description:
            self.description = other.description
        if len(other.title or '') > len(self.title or ''):
            self.title = other.title
        if other.is_live:
            self.is_live = True
        if self.transcript_status == 'UNKNOWN' and other.transcript_status != 'UNKNOWN':
            self.transcript_status = other.transcript_status
        self.providers_seen = list(dict.fromkeys(self.providers_seen + other.providers_seen))
        for key, value in other.metadata.items():
            self.metadata.setdefault(key, value)
        return self

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'duration_seconds': self.duration_seconds,
            'views': self.views,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'channel': self.channel,
            'channel_id': self.channel_id,
            'provider': self.provider,
            'providers_seen': list(self.providers_seen),
            'description': self.description,
            'is_live': self.is_live,
            'transcript_status': self.transcript_status,
            'metadata': dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('A source candidate must be a mapping')
        return cls(
            id=data.get('id'), title=data.get('title') or 'Untitled video',
            url=data.get('url') or '', duration_seconds=data.get('duration_seconds'),
            views=data.get('views'), upload_date=parse_datetime(data.get('upload_date')),
            channel=data.get('channel'), provider=data.get('provider') or 'unknown',
            channel_id=data.get('channel_id'), description=data.get('description'),
            is_live=bool(data.get('is_live')),
            transcript_status=data.get('transcript_status') or 'UNKNOWN',
            providers_seen=list(data.get('providers_seen') or []),
            metadata=dict(data.get('metadata') or {}))


@dataclass
class ProviderStatus:
    """The visible outcome of one provider attempt."""

    provider: str
    status: str
    results: int = 0
    error_code: str | None = None
    message: str = ''
    duration_ms: int = 0
    queries: list[str] = field(default_factory=list)

    def to_dict(self):
        return {'provider': self.provider, 'status': self.status, 'results': self.results,
                'error_code': self.error_code, 'message': self.message,
                'duration_ms': self.duration_ms, 'queries': list(self.queries)}


@dataclass
class QueryStatus:
    """The visible outcome of one query across the providers that ran it."""

    query: str
    provider: str
    status: str
    results: int = 0
    error_code: str | None = None
    duration_ms: int = 0
    from_cache: bool = False

    def to_dict(self):
        return {'query': self.query, 'provider': self.provider, 'status': self.status,
                'results': self.results, 'error_code': self.error_code,
                'duration_ms': self.duration_ms, 'from_cache': self.from_cache}


@dataclass
class DiscoveryDiagnostics:
    """Everything one discovery run needs to explain itself."""

    run_id: str
    niche: str = ''
    mode: str = 'balanced'
    providers: list[ProviderStatus] = field(default_factory=list)
    queries: list[QueryStatus] = field(default_factory=list)
    candidates_found: int = 0
    duplicates_removed: int = 0
    eligible: dict = field(default_factory=dict)
    rejected: dict = field(default_factory=dict)
    tier_used: str | None = None
    cache_hits: int = 0
    duration_ms: int = 0
    shortfall: int = 0
    meets_minimum: bool = False

    def add_provider(self, status):
        self.providers.append(status)

    def add_query(self, status):
        self.queries.append(status)

    def count_rejection(self, reason, amount=1):
        if amount:
            self.rejected[reason] = self.rejected.get(reason, 0) + amount

    def count_eligible(self, tier, amount=1):
        if amount:
            self.eligible[tier] = self.eligible.get(tier, 0) + amount

    @property
    def provider_failures(self):
        return sum(1 for item in self.providers if item.status in ('failed', 'timeout'))

    def to_dict(self):
        return {
            'run_id': self.run_id,
            'niche': self.niche,
            'mode': self.mode,
            'providers': [item.to_dict() for item in self.providers],
            'queries': [item.to_dict() for item in self.queries],
            'candidates_found': self.candidates_found,
            'duplicates_removed': self.duplicates_removed,
            'eligible': dict(self.eligible),
            'rejected': dict(self.rejected),
            'tier_used': self.tier_used,
            'shortfall': self.shortfall,
            'meets_minimum': self.meets_minimum,
            'provider_failures': self.provider_failures,
            'cache_hits': self.cache_hits,
            'duration_ms': self.duration_ms,
        }


class DiscoveryError(Exception):
    """A structured discovery failure that never hides the reason."""

    def __init__(self, code, message, *, diagnostics=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics

    def as_dict(self):
        data = {'error': self.code, 'message': self.message}
        if self.diagnostics is not None:
            data.update(self.diagnostics)
        return data
