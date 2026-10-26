import pytest


def test_cache_keys_are_stable_and_scope_kind_and_identity():
    from app.repositories.cache import cache_key
    identity = {'video_id': 'abc123', 'range': [10, 20]}
    assert cache_key('section', identity) == cache_key('section', {'range': [10, 20], 'video_id': 'abc123'})
    assert cache_key('transcript', identity) != cache_key('section', identity)
    assert cache_key('section', identity) != cache_key('section', {**identity, 'range': [10, 21]})


def test_json_cache_round_trips_and_expires(tmp_path):
    from app.repositories.cache import CacheRepository
    cache = CacheRepository(tmp_path / 'cache.db')
    identity = {'video_id': 'abc123', 'parser_version': 1}
    cache.put_json('transcript', identity, {'segments': [{'start': 1.25, 'text': 'hello'}]}, ttl_seconds=3600)
    assert cache.get_json('transcript', identity) == {'segments': [{'start': 1.25, 'text': 'hello'}]}
    with cache.db.connection(write=True) as db:
        db.execute('UPDATE cache_entries SET expires_at=?', ('2000-01-01T00:00:00+00:00',))
    assert cache.get_json('transcript', identity) is None


def test_file_cache_checks_integrity_before_reuse(tmp_path):
    from app.repositories.cache import CacheRepository
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'bounded media section')
    cache = CacheRepository(tmp_path / 'cache.db')
    identity = {'video_id': 'abc123', 'start': 10, 'duration': 30}
    cache.put_file('downloaded_section', identity, source, ttl_seconds=3600)
    assert cache.get_file('downloaded_section', identity) == source.resolve()
    source.write_bytes(b'corrupt')
    assert cache.get_file('downloaded_section', identity) is None


def test_file_cache_finds_only_integrity_valid_containing_sections(tmp_path):
    from app.repositories.cache import CacheRepository
    cache = CacheRepository(tmp_path / 'cache.db')
    path = tmp_path / 'wide.mp4'
    path.write_bytes(b'complete bounded section')
    identity = {'youtube_video_id': 'abc123', 'source_offset': 590,
                'requested_end': 650, 'format': 'bounded-audio-video-v1'}
    cache.put_file('downloaded_section', identity, path, ttl_seconds=3600)

    hit = cache.find_file('downloaded_section', lambda key: (
        key.get('youtube_video_id') == 'abc123' and key.get('source_offset', 0) <= 600
        and key.get('requested_end', 0) >= 620))
    assert hit == (path.resolve(), identity)
    assert cache.find_file('downloaded_section', lambda key: key.get('youtube_video_id') == 'other') is None
    path.write_bytes(b'corrupt')
    assert cache.find_file('downloaded_section', lambda key: key.get('youtube_video_id') == 'abc123') is None


def test_cache_access_telemetry_reports_hits_misses_and_reused_bytes(tmp_path):
    from app.repositories.cache import CacheRepository
    cache = CacheRepository(tmp_path / 'cache.db')
    cache.record_access('downloaded_section', 'exact_hit', reused_bytes=1200, requested_seconds=30)
    cache.record_access('downloaded_section', 'containing_hit', reused_bytes=2400, requested_seconds=20)
    cache.record_access('downloaded_section', 'miss')

    report = cache.stats()
    assert report['requests'] == 3
    assert report['hits'] == 2 and report['misses'] == 1
    assert report['hit_rate'] == pytest.approx(2 / 3)
    assert report['bytes_reused'] == 3600
    assert report['by_kind']['downloaded_section']['containing_hits'] == 1


def test_cache_rejects_non_json_or_oversized_payloads(tmp_path):
    import pytest
    from app.repositories.cache import CacheRepository
    cache = CacheRepository(tmp_path / 'cache.db')
    with pytest.raises(ValueError):
        cache.put_json('metadata', {'id': 'x'}, {'bad': float('nan')}, ttl_seconds=60)
    with pytest.raises(ValueError):
        cache.put_json('metadata', {'id': 'x'}, {'data': 'x' * 100}, ttl_seconds=60, max_bytes=32)
