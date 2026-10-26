"""Discovery engine tests.

Every provider in this file is synthetic. The suite never contacts YouTube.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from clipping.discovery.cache import DiscoveryCache
from clipping.discovery.eligibility import EligibilityEngine
from clipping.discovery.engine import DiscoveryEngine, DiscoveryOutcome
from clipping.discovery.models import SourceCandidate
from clipping.discovery.providers import DiscoveryProvider, ProviderError, PublicSearchProvider
from clipping.discovery.queries import QueryGenerator
from clipping.discovery.scoring import SourceScorer


def published(hours=24):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def record(identifier='abcdefghijk', views=200000, minutes=60, hours=24,
           title='Business podcast interview'):
    """One public provider record."""
    return {'id': identifier, 'title': title, 'uploader': 'Creator',
            'published_at': published(hours), 'view_count': views,
            'duration': minutes * 60, 'live_status': 'not_live'}


class FakeProvider(DiscoveryProvider):
    """A provider that answers from a fixture instead of the network."""

    def __init__(self, name, records=(), error=None):
        self.name = name
        self.records = list(records)
        self.error = error
        self.queries = []

    def search_records(self, query, limit):
        self.queries.append(query)
        if self.error:
            raise ProviderError(self.error, 'The provider did not answer')
        return self.records[:limit]


class Settings:
    """A minimal settings object carrying a discovery block."""

    def __init__(self, **discovery):
        self.discovery = discovery


def engine(providers, **discovery):
    discovery.setdefault('queries_per_niche', 1)
    discovery.setdefault('target_sources', 5)
    discovery.setdefault('minimum_sources', 2)
    return DiscoveryEngine(settings=Settings(**discovery), providers=list(providers))


NICHE = {'name': 'Business', 'query': 'business podcast full episode'}


def test_a_failing_provider_does_not_stop_the_next_provider():
    failing = FakeProvider('first', error='PROVIDER_FAILED')
    working = FakeProvider('second', [record()])
    outcome = engine([failing, working]).discover(NICHE)
    assert outcome.ok
    assert [item.id for item in outcome.sources] == ['abcdefghijk']
    statuses = {item['provider']: item['status'] for item in outcome.providers}
    assert statuses == {'first': 'failed', 'second': 'success'}
    assert outcome.diagnostics['provider_failures'] == 1


def test_a_provider_timeout_is_reported_with_its_own_code():
    slow = FakeProvider('slow', error='PROVIDER_TIMEOUT')
    outcome = engine([slow]).discover(NICHE)
    assert not outcome.ok
    assert outcome.error['error'] == 'ALL_PROVIDERS_FAILED'
    assert outcome.error['providers_attempted'] == ['slow']
    assert outcome.providers[0]['error_code'] == 'PROVIDER_TIMEOUT'


def test_the_same_provider_and_query_runs_once_per_discovery():
    provider = FakeProvider('one', [record()])
    discovery = engine([provider], queries_per_niche=3)
    discovery.discover(NICHE)
    assert len(provider.queries) == len(set(provider.queries))


def test_duplicate_videos_from_two_providers_become_one_candidate():
    first = FakeProvider('first', [record(), record('lmnopqrstuv')])
    second = FakeProvider('second', [record()])
    outcome = engine([first, second]).discover(NICHE)
    assert outcome.ok
    assert sorted(item.id for item in outcome.sources) == ['abcdefghijk', 'lmnopqrstuv']
    merged = next(item for item in outcome.sources if item.id == 'abcdefghijk')
    assert set(merged.providers_seen) == {'first', 'second'}
    assert len(merged.providers_seen) == 2
    assert outcome.diagnostics['duplicates_removed'] == 1
    assert outcome.diagnostics['candidates_found'] == 2


def test_strict_rules_relax_until_a_source_is_found():
    smaller = FakeProvider('one', [record(views=50000, minutes=30, hours=72)])
    outcome = engine([smaller], target_sources=5).discover(NICHE)
    assert outcome.ok
    assert outcome.tier == 'medium'
    assert outcome.diagnostics['eligible'].get('strict', 0) == 0
    assert outcome.diagnostics['eligible']['medium'] == 1
    assert outcome.diagnostics['rejected']['duration'] >= 1


def test_a_source_below_every_tier_reports_its_reasons():
    tiny = FakeProvider('one', [record(views=100, minutes=5, hours=24 * 30)])
    outcome = engine([tiny], target_sources=5).discover(NICHE)
    assert not outcome.ok
    assert outcome.error['error'] == 'NO_SUITABLE_SOURCES'
    assert outcome.error['candidates_found'] == 1
    assert outcome.error['reason_counts']['duration'] >= 1
    unpopular = FakeProvider('one', [record(views=100, minutes=60, hours=24)])
    outcome = engine([unpopular], target_sources=5).discover(NICHE)
    assert outcome.error['error'] == 'NO_SUITABLE_SOURCES'
    assert outcome.error['reason_counts']['views'] >= 1


def test_missing_metadata_is_counted_not_crashed():
    partial = FakeProvider('one', [{'id': 'abcdefghijk', 'title': 'Business podcast'}])
    outcome = engine([partial], target_sources=5).discover(NICHE)
    assert not outcome.ok
    assert outcome.error['candidates_found'] == 1
    reasons = outcome.error['reason_counts']
    assert reasons.get('duration_unknown', 0) >= 1
    assert outcome.error['reason_counts'] == reasons


def test_an_unknown_transcript_status_is_not_a_rejection():
    candidate = SourceCandidate(id='abcdefghijk', title='Business podcast',
                                 url='https://www.youtube.com/watch?v=abcdefghijk',
                                 duration_seconds=3600, views=200000,
                                 upload_date=datetime.now(timezone.utc) - timedelta(days=1),
                                 transcript_status='UNKNOWN')
    tier = EligibilityEngine().tiers['strict']
    accepted, reason = EligibilityEngine().evaluate(candidate, tier, 0.95)
    assert accepted and reason is None


def test_all_providers_failing_returns_a_structured_error():
    outcome = engine([FakeProvider('one', error='PROVIDER_FAILED'),
                       FakeProvider('two', error='PROVIDER_TIMEOUT')]).discover(NICHE)
    assert not outcome.ok
    assert outcome.error['error'] == 'ALL_PROVIDERS_FAILED'
    assert outcome.error['providers_attempted'] == ['one', 'two']
    assert outcome.error['queries_attempted'] == 1
    assert outcome.error['reason_counts'] == {}


def test_query_generation_returns_distinct_variants():
    queries = QueryGenerator(queries_per_niche=8).generate(NICHE, 8)
    assert len(queries) == len(set(queries)) == 8
    assert NICHE['query'] in queries
    assert any('interview' in query for query in queries)
    expanded = QueryGenerator(queries_per_niche=8).expand(NICHE, queries)
    assert expanded and not set(expanded) & set(queries)


def test_the_scorer_ranks_by_observed_signals():
    scorer = SourceScorer()
    strong = SourceCandidate(id='abcdefghijk', title='Business podcast interview',
                              url='https://www.youtube.com/watch?v=abcdefghijk',
                              duration_seconds=3600, views=400000,
                              upload_date=datetime.now(timezone.utc) - timedelta(hours=12))
    weak = SourceCandidate(id='lmnopqrstuv', title='Business podcast interview',
                            url='https://www.youtube.com/watch?v=lmnopqrstuv',
                            duration_seconds=3600, views=1000,
                            upload_date=datetime.now(timezone.utc) - timedelta(days=9))
    ranked = scorer.rank([weak, strong], 'business podcast')
    assert ranked[0][0].id == 'abcdefghijk'
    assert ranked[0][1]['score'] > ranked[1][1]['score']
    assert 'missing_signals' in ranked[0][1]


def test_a_cached_result_is_reused_and_an_expired_result_is_refetched(tmp_path):
    from app.repositories.cache import CacheRepository
    repository = CacheRepository(tmp_path / 'cache.db')
    cache = DiscoveryCache(repository=repository, ttl_hours=3)
    provider = FakeProvider('one', [record()])
    discovery = DiscoveryEngine(settings=Settings(queries_per_niche=1), providers=[provider],
                                cache=cache)
    discovery.discover(NICHE)
    discovery.discover(NICHE)
    assert len(provider.queries) == 1
    assert cache.stats()['hits'] == 1
    with repository.db.connection(write=True) as db:
        db.execute('UPDATE cache_entries SET expires_at=?', ('2000-01-01T00:00:00+00:00',))
    discovery.discover(NICHE)
    assert len(provider.queries) == 2


def test_the_public_provider_reads_a_search_page_without_a_key(monkeypatch):
    body = json.dumps({'videoId': 'abcdefghijk',
                       'title': {'runs': [{'text': 'Business podcast episode'}]},
                       'lengthText': {'simpleText': '1:02:03'},
                       'viewCountText': {'simpleText': '12,345 views'}})
    monkeypatch.setattr('clipping.discovery.providers.urlopen',
                        lambda *args, **kwargs: _Response(body))
    candidates = PublicSearchProvider().search('business podcast', 5)
    assert len(candidates) == 1
    assert candidates[0].id == 'abcdefghijk'
    assert candidates[0].duration_seconds == 3723
    assert candidates[0].views == 12345


def test_discovery_never_downloads_media(monkeypatch):
    from clipping import media
    from clipping.discovery.providers import YtDlpProvider
    calls = []

    def command(args, **options):
        calls.append((args, options))
        return json.dumps({'entries': []})

    monkeypatch.setattr(media, 'command', command)
    assert YtDlpProvider(timeout=30).search_records('business podcast', 20) == []
    args, options = calls[0]
    assert '--skip-download' in args and '--flat-playlist' in args
    assert args[-1].startswith('ytsearch20:')
    assert options['timeout'] <= 30


def test_pipeline_records_carry_the_fields_the_clip_pipeline_needs():
    from clipping.discovery import pipeline
    candidate = SourceCandidate(id='abcdefghijk', title='Business podcast',
                                 url='https://www.youtube.com/watch?v=abcdefghijk',
                                 duration_seconds=3600, views=200000,
                                 upload_date=datetime.now(timezone.utc) - timedelta(days=1),
                                 channel='Creator')
    record_out = pipeline.source_record(candidate, NICHE, score=0.81, tier='strict')
    assert record_out['id'] == 'abcdefghijk'
    assert record_out['url'].endswith('abcdefghijk')
    assert record_out['eligible_preview'] is True
    assert record_out['published_at'] and record_out['duration'] == 3600
    assert record_out['views_per_hour_since_upload'] > 0
    assert record_out['source_score'] == 0.81 and record_out['eligibility_tier'] == 'strict'
    unknown = SourceCandidate(id='lmnopqrstuv', title='Unknown metadata',
                               url='https://www.youtube.com/watch?v=lmnopqrstuv')
    assert pipeline.source_record(unknown, NICHE)['eligible_preview'] is False


def test_the_discover_command_reports_diagnostics_without_starting_clips(tmp_path, monkeypatch, capsys):
    from clipping import cli
    from clipping.discovery import service
    candidate = SourceCandidate(id='abcdefghijk', title='Business podcast',
                                url='https://www.youtube.com/watch?v=abcdefghijk',
                                duration_seconds=3600, views=200000,
                                upload_date=datetime.now(timezone.utc) - timedelta(days=1))
    outcome = DiscoveryOutcome(run_id='run-1', niche='Business', mode='balanced',
                                sources=[candidate], tier='strict',
                                queries=['business podcast'], providers=[],
                                diagnostics={'candidates_found': 3, 'rejected': {'views': 2}})
    monkeypatch.setattr(service, 'discover', lambda *args, **kwargs: outcome)
    assert cli.main(['--storage', str(tmp_path), 'discover', '--niche', 'Business',
                     '--dry-run']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['clips_started'] is False
    assert payload['tier'] == 'strict'
    assert payload['diagnostics']['candidates_found'] == 3
    assert payload['sources'][0]['id'] == 'abcdefghijk'


def test_the_controller_broadens_the_search_when_the_scan_finds_nothing(tmp_path, monkeypatch):
    from clipping import orchestrator, trends
    from clipping.discovery import pipeline
    from clipping.workflow import ClippingWorkflow
    monkeypatch.setattr(trends, 'discover', lambda niche: [])
    engine_db = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    research = trends.TrendResearchAgent(engine_db)
    candidate = SourceCandidate(id='abcdefghijk', title='Business podcast',
                                url='https://www.youtube.com/watch?v=abcdefghijk',
                                duration_seconds=3600, views=200000,
                                upload_date=datetime.now(timezone.utc) - timedelta(days=1))
    supplement = pipeline.source_record(candidate, trends.NICHES[0])
    monkeypatch.setattr(pipeline, 'supplement', lambda *args, **kwargs: ([supplement], []))
    controller = orchestrator.Controller(tmp_path, orchestrator.Config(provider='public'))
    scan = controller.search(research)
    assert [item['id'] for item in scan['results']] == ['abcdefghijk']
    assert scan['results'][0]['eligible_preview'] is True
    assert controller.state['discovery_supplement']['sources'] == 1


def test_a_scan_with_a_usable_source_does_not_broaden_the_search(tmp_path, monkeypatch):
    from clipping import orchestrator, trends
    from clipping.discovery import pipeline
    from clipping.workflow import ClippingWorkflow
    monkeypatch.setattr(trends, 'discover', lambda niche: [record()])
    monkeypatch.setattr(pipeline, 'supplement', lambda *args, **kwargs: pytest.fail(
        'The broad search must not repeat a successful scan'))
    engine_db = ClippingWorkflow(tmp_path / 'jobs.db', tmp_path / 'storage')
    research = trends.TrendResearchAgent(engine_db)
    controller = orchestrator.Controller(tmp_path, orchestrator.Config(provider='public'))
    scan = controller.search(research)
    assert scan['results']
    assert 'discovery_supplement' not in controller.state


class _Response:
    """A minimal readable response for the public search provider."""

    def __init__(self, body):
        self.body = body.encode('utf-8')

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
