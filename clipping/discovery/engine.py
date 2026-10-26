"""The discovery engine.

The engine is the only place that knows the whole flow:

    niche -> query expansion -> provider fallback -> broad results
          -> candidate normalization -> deduplication -> progressive eligibility
          -> source scoring -> top sources

A provider failure never ends the run. A zero-result run always explains
itself with structured reasons. Discovery never downloads media.
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from clipping.discovery.cache import DiscoveryCache
from clipping.discovery.eligibility import EligibilityEngine
from clipping.discovery.health import ProviderHealth
from clipping.discovery.models import (DiscoveryDiagnostics, ProviderStatus, QueryStatus,
                                       SourceCandidate, parse_datetime)
from clipping.discovery.providers import (PROVIDER_ORDER, ProviderError, PublicSearchProvider,
                                           SeleniumProvider, YouTubeApiProvider, YtDlpProvider)
from clipping.discovery.queries import QueryGenerator
from clipping.discovery.scoring import SourceScorer

MODES = {
    'fast': {'queries': 3, 'providers': ('yt_dlp',), 'secondary_lookups': 0},
    'balanced': {'queries': None, 'providers': PROVIDER_ORDER, 'secondary_lookups': 3},
    'deep': {'queries': None, 'providers': PROVIDER_ORDER, 'secondary_lookups': 8},
}


@dataclass
class DiscoveryOutcome:
    """The result of one discovery run."""

    run_id: str
    niche: str = ''
    mode: str = 'balanced'
    sources: list = field(default_factory=list)
    tier: str | None = None
    queries: list = field(default_factory=list)
    providers: list = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)
    error: dict | None = None

    @property
    def ok(self):
        return bool(self.sources) and self.error is None

    def as_dict(self):
        return {'run_id': self.run_id, 'niche': self.niche, 'mode': self.mode,
                'tier': self.tier, 'queries': list(self.queries),
                'sources': [item.to_dict() for item in self.sources],
                'diagnostics': self.diagnostics, 'error': self.error}


def _provider_config(settings):
    discovery = getattr(settings, 'discovery', None)
    if discovery is None:
        return {}
    return discovery.model_dump() if hasattr(discovery, 'model_dump') else dict(discovery)


def _niche_name(niche):
    if isinstance(niche, dict):
        return str(niche.get('name') or '')
    return str(niche or '')


def _niche_query(niche):
    if isinstance(niche, dict):
        return str(niche.get('query') or '')
    return ''


def _record_dict(item):
    """Keep only the public fields the engine understands."""
    if not isinstance(item, dict):
        return {}
    record = {}
    for key in ('id', 'title', 'uploader', 'channel', 'channel_id', 'published_at',
                'upload_date', 'live_status'):
        value = item.get(key)
        if isinstance(value, str):
            record[key] = value[:600]
    for key in ('view_count', 'duration', 'timestamp', 'like_count', 'comment_count'):
        value = item.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            record[key] = value
    description = item.get('description')
    if isinstance(description, str):
        record['description'] = description[:600]
    if isinstance(item.get('is_live'), bool):
        record['is_live'] = item['is_live']
    return record


def _candidate_from_record(record, provider):
    identifier = record.get('id')
    if not isinstance(identifier, str):
        return None
    published = (parse_datetime(record.get('published_at')) or parse_datetime(record.get('upload_date'))
                 or parse_datetime(record.get('timestamp')))
    try:
        return SourceCandidate(
            id=identifier, title=record.get('title') or 'Untitled video',
            url='https://www.youtube.com/watch?v=' + identifier,
            duration_seconds=record.get('duration'), views=record.get('view_count'),
            upload_date=published, channel=record.get('uploader') or record.get('channel'),
            provider=provider, channel_id=record.get('channel_id'),
            description=record.get('description'),
            is_live=bool(record.get('is_live')) or record.get('live_status') in
            ('is_live', 'is_upcoming', 'post_live'),
            transcript_status='UNKNOWN',
            metadata={key: record[key] for key in ('like_count', 'comment_count') if key in record})
    except ValueError:
        return None


def _tiers(config):
    from clipping.discovery.eligibility import DEFAULT_TIERS, EligibilityTier
    configured = config.get('eligibility') or {}
    tiers = {}
    for name, values in configured.items():
        if not isinstance(values, dict):
            continue
        tiers[name] = EligibilityTier(
            name=name,
            min_duration_minutes=int(values.get('min_duration_minutes', 30)),
            min_views=int(values.get('min_views', 25000)),
            max_age_days=int(values.get('max_age_days', 30)),
            min_score=float(values.get('min_score', 0.55)),
            require_views=bool(values.get('require_views', name != 'relaxed')),
            require_age=bool(values.get('require_age', name == 'strict')))
    return tiers or DEFAULT_TIERS


class DiscoveryEngine:
    """Run a resilient, observable source discovery."""

    def __init__(self, *, settings=None, providers=None, cache=None, health=None,
                 history=None, event=None):
        self.settings = settings
        self.config = _provider_config(settings)
        self.event = event or (lambda name, **fields: None)
        self.health = health or ProviderHealth()
        self.cache = cache if cache is not None else DiscoveryCache(
            repository=None, ttl_hours=int(self.config.get('cache_ttl_hours', 3)))
        self.history = history
        self.scorer = SourceScorer(
            weights=self.config.get('scoring_weights'),
            freshness_window_days=int(self.config.get('freshness_window_days', 14)))
        self.queries = QueryGenerator(
            families=tuple(self.config.get('families') or QueryGenerator().families),
            queries_per_niche=int(self.config.get('queries_per_niche', 8)))
        self._providers = list(providers) if providers is not None else None

    # -- provider chain ---------------------------------------------------

    def build_providers(self, mode='balanced'):
        if self._providers is not None:
            return list(self._providers)
        settings = self.config
        enabled = settings.get('providers') or {}
        timeout = int(settings.get('provider_timeout_seconds', 20))
        region = settings.get('region', 'US')
        language = settings.get('language', 'en')
        chain = []
        allowed = MODES.get(mode, MODES['balanced'])['providers']
        for name in PROVIDER_ORDER:
            if name not in allowed:
                continue
            if enabled.get(name) is False:
                continue
            if name == 'youtube_api':
                from clipping import trends
                chain.append(YouTubeApiProvider(api=trends.youtube_api, region=region,
                                                language=language, timeout=timeout))
            elif name == 'yt_dlp':
                chain.append(YtDlpProvider(timeout=timeout))
            elif name == 'selenium':
                chain.append(SeleniumProvider(timeout=max(timeout, 60)))
            else:
                chain.append(PublicSearchProvider(timeout=timeout, region=region, language=language))
        return chain

    # -- run ---------------------------------------------------------------

    def discover(self, niche, *, mode='balanced', region=None, language=None, use_cache=True,
                 dry_run=False, debug=False):
        mode = mode if mode in MODES else 'balanced'
        settings = self.config
        region = region or settings.get('region', 'US')
        language = language or settings.get('language', 'en')
        run_id = str(uuid.uuid4())
        diagnostics = DiscoveryDiagnostics(run_id=run_id, niche=_niche_name(niche), mode=mode)
        started = time.monotonic()
        name = _niche_name(niche)
        keywords = ' '.join(filter(None, [name, _niche_query(niche)]))
        query_limit = MODES[mode]['queries'] or int(settings.get('queries_per_niche', 8))
        queries = self.queries.generate(niche, query_limit)
        self.event('discovery_started', run_id=run_id, niche=name, mode=mode, queries=len(queries))
        chain = self.build_providers(mode)
        order = self.health.order([item.name for item in chain])
        available = {item.name: item for item in chain}
        chain = [available[item] for item in order if item in available]

        limit = int(settings.get('results_per_query', 20))
        max_parallel = max(1, int(settings.get('max_parallel_queries', 3)))
        tasks, pairs = [], set()
        for provider in chain:
            for query in queries:
                key = (provider.name, query)
                if key in pairs:
                    continue
                pairs.add(key)
                tasks.append((provider, query))
        outcomes = []
        if tasks:
            total_timeout = max(1, int(settings.get('total_timeout_seconds', 90)))
            executor = ThreadPoolExecutor(max_workers=max_parallel)
            try:
                futures = {executor.submit(self._run_query, provider, query, limit,
                                           region, language, use_cache): (provider, query)
                           for provider, query in tasks}
                finished, pending = wait(futures, timeout=total_timeout)
                for future in finished:
                    outcomes.append(future.result())
                for future in pending:
                    # A hanging provider must not block the whole pipeline.
                    future.cancel()
                    provider, query = futures[future]
                    outcomes.append({'provider': provider.name, 'query': query, 'status': 'timeout',
                                     'candidates': [], 'cached': False,
                                     'error_code': 'PROVIDER_TIMEOUT'})
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        pool, seen = [], {}
        for outcome in outcomes:
            diagnostics.add_query(QueryStatus(query=outcome['query'], provider=outcome['provider'],
                                             status=outcome['status'], results=len(outcome['candidates']),
                                             error_code=outcome.get('error_code'),
                                             from_cache=outcome.get('cached', False)))
            if outcome.get('cached'):
                diagnostics.cache_hits += 1
            for candidate in outcome['candidates']:
                existing = seen.get(candidate.id)
                if existing is not None:
                    existing.merge(candidate)
                    diagnostics.duplicates_removed += 1
                    continue
                seen[candidate.id] = candidate
                pool.append(candidate)
        diagnostics.candidates_found = len(pool)

        for provider in chain:
            events = [item for item in diagnostics.queries if item.provider == provider.name]
            successes = [item for item in events if item.status == 'success']
            failures = [item for item in events if item.status in ('failed', 'timeout')]
            if not events:
                diagnostics.add_provider(ProviderStatus(provider=provider.name, status='skipped',
                                                       message='No query reached this provider'))
                continue
            if successes:
                found = sum(item.results for item in successes)
                diagnostics.add_provider(ProviderStatus(
                    provider=provider.name, status='success', results=found,
                    queries=[item.query for item in successes]))
                self.health.record_success(provider.name, found)
            else:
                code = failures[0].error_code or 'PROVIDER_FAILED'
                diagnostics.add_provider(ProviderStatus(
                    provider=provider.name, status='failed', error_code=code,
                    message='The provider did not return usable results',
                    queries=[item.query for item in failures]))
                self.health.record_failure(provider.name, code)

        if not pool:
            diagnostics.duration_ms = int((time.monotonic() - started) * 1000)
            error = self._structured_error(diagnostics, 'ALL_PROVIDERS_FAILED')
            self.event('discovery_failed', run_id=run_id, error_code='ALL_PROVIDERS_FAILED')
            return DiscoveryOutcome(run_id=run_id, niche=name, mode=mode, queries=queries,
                                    providers=[item.to_dict() for item in diagnostics.providers],
                                    diagnostics=diagnostics.to_dict(), error=error)

        pool = self._secondary_lookup(pool, mode)
        scores, ranked = {}, []
        for candidate, report in self.scorer.rank(pool, keywords):
            scores[candidate.id] = report['score']
            ranked.append((candidate, report))
        engine = EligibilityEngine(tiers=_tiers(settings),
                                    whitelist_boost=float(settings.get('whitelist_boost', 0.0)),
                                    blacklist=self._blacklist())
        selection = engine.select(pool, scores,
                                  target=int(settings.get('target_sources', 5)),
                                  minimum=int(settings.get('minimum_sources', 2)),
                                  whitelisted=self._whitelisted(pool))
        for tier_name, count in selection['counts'].items():
            diagnostics.count_eligible(tier_name, count)
        for reason, count in selection['rejected'].items():
            diagnostics.count_rejection(reason, count)
        diagnostics.tier_used = selection['tier']
        diagnostics.shortfall = selection['shortfall']
        diagnostics.meets_minimum = selection['meets_minimum']
        chosen = {item.id for item in selection['selected']}
        sources = [candidate for candidate, _ in ranked if candidate.id in chosen]
        if not sources:
            diagnostics.duration_ms = int((time.monotonic() - started) * 1000)
            error = self._structured_error(diagnostics, 'NO_SUITABLE_SOURCES')
            self.event('discovery_failed', run_id=run_id, error_code='NO_SUITABLE_SOURCES')
            return DiscoveryOutcome(run_id=run_id, niche=name, mode=mode, queries=queries,
                                    providers=[item.to_dict() for item in diagnostics.providers],
                                    diagnostics=diagnostics.to_dict(), error=error)
        if not dry_run and self.history is not None:
            for candidate in pool:
                self.history.consider(candidate.id, channel=candidate.channel, title=candidate.title)
            for candidate in sources:
                self.history.select(candidate.id)
            for query in queries:
                self.history.record_query(query, results=len(pool), eligible=len(sources))
        diagnostics.duration_ms = int((time.monotonic() - started) * 1000)
        payload = diagnostics.to_dict()
        if debug:
            payload['debug'] = {
                'scored': [{'id': candidate.id, 'score': report['score'],
                            'missing_signals': report['missing_signals']}
                           for candidate, report in ranked],
                'cache': self.cache.stats(),
                'provider_health': self.health.report()}
        self.event('discovery_completed', run_id=run_id, sources=len(sources),
                   tier=selection['tier'], duration_ms=diagnostics.duration_ms)
        return DiscoveryOutcome(run_id=run_id, niche=name, mode=mode, sources=sources,
                                tier=selection['tier'], queries=queries,
                                providers=[item.to_dict() for item in diagnostics.providers],
                                diagnostics=payload)

    # -- internals ---------------------------------------------------------

    def _cache_identity(self):
        """A stable identity of the active rules, so a changed rule never reuses a stale result."""
        return {key: value for key, value in self.config.items()
                if key not in ('cache_ttl_hours', 'cache_identity')}

    def _run_query(self, provider, query, limit, region, language, use_cache):
        cached = False
        records = None
        identity = self._cache_identity()
        if use_cache:
            cached_records = self.cache.get(query, provider.name, region, language, identity)
            if cached_records is not None:
                records = cached_records
                cached = True
        if records is None:
            try:
                raw = provider.search_records(query, limit)
                records = [_record_dict(item) for item in raw]
                if use_cache:
                    self.cache.put(query, provider.name, region, language, records, identity)
            except ProviderError as exc:
                return {'provider': provider.name, 'query': query, 'status': 'failed',
                        'candidates': [], 'cached': False, 'error_code': exc.code}
            except Exception:  # noqa: BLE001 - a provider crash must not end discovery.
                return {'provider': provider.name, 'query': query, 'status': 'failed',
                        'candidates': [], 'cached': False, 'error_code': 'PROVIDER_FAILED'}
        candidates = []
        for item in records:
            candidate = _candidate_from_record(item, provider.name)
            if candidate is not None:
                candidates.append(candidate)
        return {'provider': provider.name, 'query': query, 'status': 'success',
                'candidates': candidates, 'cached': cached, 'error_code': None}

    def _secondary_lookup(self, pool, mode):
        limit = int(self.config.get('secondary_lookup_limit', MODES[mode]['secondary_lookups']))
        if limit <= 0:
            return pool
        uncertain = [item for item in pool
                     if item.duration_seconds is None or item.views is None or item.upload_date is None]
        uncertain.sort(key=lambda item: -(item.views or 0))
        from clipping.discovery.providers import DiscoveryProvider
        lookup = next((provider for provider in self.build_providers(mode)
                       if type(provider).lookup is not DiscoveryProvider.lookup), None)
        if lookup is None:
            return pool
        for candidate in uncertain[:limit]:
            details = lookup.lookup(candidate.id)
            if not isinstance(details, dict):
                continue
            enriched = DiscoveryProvider._candidate(details, lookup.name)
            if enriched is not None:
                candidate.merge(enriched)
        return pool

    def _blacklist(self):
        if self.history is None:
            return ()
        return self.history.blacklist_ids()

    def _whitelisted(self, pool):
        if self.history is None:
            return ()
        boosts = self.history.whitelist_boosts()
        return {candidate.id for candidate in pool
                if candidate.channel_id and candidate.channel_id in boosts}

    def _structured_error(self, diagnostics, code):
        return {'error': code,
                'providers_attempted': [item.provider for item in diagnostics.providers
                                        if item.status != 'skipped'],
                'queries_attempted': len({item.query for item in diagnostics.queries}),
                'candidates_found': diagnostics.candidates_found,
                'reason_counts': dict(diagnostics.rejected),
                'provider_failures': diagnostics.provider_failures}
