import json
import re
import shutil

import pytest


def sections_module():
    from clipping import sections
    return sections


@pytest.mark.parametrize(('message', 'kind', 'reason', 'status'), [
    ('Server returned 503 Service Unavailable', 'SourceUnavailable', 'http_unavailable', 503),
    ('HTTP Error 429: Too Many Requests', 'SourceUnavailable', 'rate_limited', 429),
    ('Unable to connect to proxy', 'SourceUnavailable', 'proxy_unavailable', None),
    ('Tunnel connection failed: 502 Bad Gateway', 'SourceUnavailable', 'proxy_unavailable', None),
    ('Temporary failure in name resolution', 'SourceUnavailable', 'dns_unavailable', None),
    ('CERTIFICATE_VERIFY_FAILED: certificate verify failed', 'SourceSetupRequired', 'tls_verification_failed', None),
    ('Unrecognized option rw_timeout', 'SourceSetupRequired', 'downloader_setup_failed', None),
    ('Install ffmpeg and make it available on PATH', 'SourceSetupRequired', 'downloader_setup_failed', None),
    ('Unknown downloader failure', 'SourceSetupRequired', 'downloader_setup_failed', None),
    ('Server returned 403 Forbidden', 'SourceAccessRequired', 'access_refused', 403),
    ('This video is private', 'SourceAccessRequired', 'access_refused', None),
    ('This video has been removed', 'SourceAccessRequired', 'access_refused', None),
])
def test_remote_failures_retain_safe_diagnostics_without_blacklisting_setup_errors(
        monkeypatch, message, kind, reason, status):
    from clipping import media
    mod = sections_module()
    def fail(*args, **kwargs):
        raise ValueError(message + ' https://media.test/?token=SECRET_SENTINEL')
    monkeypatch.setattr(media, 'command', fail)
    with pytest.raises(Exception) as error:
        mod.remote_command(['synthetic-command'], 300)
    assert type(error.value).__name__ == kind
    assert error.value.diagnostic == {
        'reason': reason, **({'http_status': status} if status is not None else {})}
    assert 'SECRET_SENTINEL' not in str(error.value) + json.dumps(error.value.diagnostic)


def test_section_timeout_exposes_bounded_diagnostic_without_signed_command_arguments(monkeypatch):
    import subprocess
    from clipping import media
    mod = sections_module()
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired(['tool', 'https://media.test/?token=SECRET_SENTINEL'], 300)
    monkeypatch.setattr(media, 'command', fail)
    with pytest.raises(media.SourceUnavailable) as error:
        mod.remote_command(['synthetic-command'], 300)
    assert error.value.diagnostic == {'reason': 'timeout', 'timeout_seconds': 300}
    assert 'SECRET_SENTINEL' not in str(error.value) + json.dumps(error.value.diagnostic)


def test_source_failure_diagnostics_reject_untrusted_codes_and_unbounded_values():
    from clipping import media
    failure = media.SourceUnavailable('Public failure', reason=['SECRET_SENTINEL'],
                                      http_status='https://media.test/?token=SECRET_SENTINEL',
                                      timeout_seconds=float('inf'))
    assert failure.diagnostic == {'reason': 'network_unavailable'}


def test_caption_first_inspection_never_requests_video_or_exposes_media_urls(tmp_path, monkeypatch):
    from clipping import media
    mod = sections_module()
    calls = []

    def command(args, **kwargs):
        calls.append(args)
        (tmp_path / 'captions.en.json3').write_text(json.dumps({'events': [
            {'tStartMs': 10000, 'dDurationMs': 4000, 'segs': [{'utf8': 'How do you build a team?'}]},
            {'tStartMs': 14000, 'dDurationMs': 8000, 'segs': [{'utf8': 'Start with people you trust.'}]}]}))
        return json.dumps({'id': 'abcdefghijk', 'title': 'Building a team', 'duration': 1800,
                           'heatmap': None, 'url': 'https://media.test/?token=SECRET'})

    monkeypatch.setattr(media, 'command', command)
    result = mod.inspect_source({'id': 'abcdefghijk', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}, tmp_path)
    assert '--skip-download' in calls[0] and '--write-auto-subs' in calls[0]
    assert '--ignore-config' in calls[0]
    assert result['segments'][0]['text'] == 'How do you build a team?'
    assert 'SECRET' not in json.dumps(result)
    assert not list(tmp_path.glob('*.mp4'))


def test_inspection_reuses_recent_cached_transcript_and_replay_metadata(tmp_path, monkeypatch):
    from clipping import media
    mod = sections_module()
    cached = {'id': 'abcdefghijk', 'title': 'Older title', 'duration': 1800,
        'segments': [{'start': 10.0, 'end': 14.0, 'text': 'A complete useful thought.'}],
        'heatmap': [{'start_time': 10, 'end_time': 14, 'value': .8}], 'view_count': 100,
        'like_count': None, 'comment_count': None, 'published_at': None, 'chapters': [],
        'transcript_origin': 'youtube_public_captions'}

    class Cache:
        def get_json(self, *args, **kwargs):
            return cached
        def put_json(self, *args, **kwargs):
            raise AssertionError('a cache hit must not rewrite its entry')

    monkeypatch.setattr(media, 'command', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('network used')))
    result = mod.inspect_source({'id': 'abcdefghijk', 'title': 'Fresh title', 'views': 200,
        'url': 'https://www.youtube.com/watch?v=abcdefghijk'}, tmp_path, cache=Cache())
    assert result['segments'] == cached['segments']
    assert result['heatmap'] == cached['heatmap']
    assert result['title'] == 'Fresh title' and result['view_count'] == 200


def test_json3_normalizes_rolling_overlap_and_rejects_empty_or_invalid_captions():
    mod = sections_module()
    data = {'events': [
        {'tStartMs': 0, 'dDurationMs': 6000, 'segs': [{'utf8': 'A complete sentence.'}]},
        {'tStartMs': 0, 'dDurationMs': 6000, 'segs': [{'utf8': 'A complete sentence.'}]},
        {'tStartMs': 4000, 'dDurationMs': 4000, 'segs': [{'utf8': 'Another clear answer.'}]},
        {'tStartMs': 8000, 'dDurationMs': 2000, 'segs': [{'utf8': '\n'}]}]}
    result = mod.parse_captions(data, 1800)
    assert len(result) == 2
    assert result[0]['end'] <= result[1]['start']
    for bad in ({}, {'events': []}, {'events': [{'tStartMs': float('nan'), 'dDurationMs': 1000, 'segs': [{'utf8': 'Bad'}]}]}):
        with pytest.raises(ValueError):
            mod.parse_captions(bad, 1800)


def test_choose_four_distinct_moments_and_accept_three_without_duplicates():
    mod = sections_module()
    segments = []
    topics = [
        ('Hire for a clear business role.', 'Write three skills before interviewing anyone.'),
        ('Cash flow keeps a business alive.', 'Keep reserves for taxes and supplier payments.'),
        ('Customers buy an outcome.', 'Explain the benefit before listing product features.'),
        ('Better meetings need decisions.', 'Assign an owner and a deadline to every action.'),
        ('Price reflects customer value.', 'Test a higher price with a small product group.'),
        ('A reliable process prevents mistakes.', 'Use a checklist before sending an order.'),
        ('Focus protects useful working time.', 'Block distractions while solving the hardest problem.'),
        ('A manager should teach judgment.', 'Explain the decision instead of issuing commands.'),
    ]
    for index, (opening, payoff) in enumerate(topics):
        start = 100 + index * 100
        segments += [{'start': start, 'end': start + 10, 'text': opening},
                     {'start': start + 10, 'end': start + 35, 'text': payoff}]
    chosen = mod.select_moments({'segments': segments, 'duration': 1800, 'title': 'Business teams'}, 4, 35)
    assert len(chosen) == 4
    for index, item in enumerate(chosen):
        a = item['clip_plan']
        for other in chosen[index + 1:]:
            b = other['clip_plan']
            assert a['start_seconds'] + a['duration_seconds'] + 3 <= b['start_seconds'] or b['start_seconds'] + b['duration_seconds'] + 3 <= a['start_seconds']
    three = mod.select_moments({'segments': segments[:6], 'duration': 1800, 'title': 'Business teams'}, 4, 35)
    assert len(three) == 3
    with pytest.raises(ValueError, match='three'):
        mod.select_moments({'segments': segments[:4], 'duration': 1800, 'title': 'Business teams'}, 4, 35)


def test_batch_rejects_repeated_takeaway_even_at_a_separate_replay_peak():
    mod = sections_module()
    pairs = [
        ('Customers buy results, not features.', 'Explain three business outcomes before listing specifications.'),
        ('CUSTOMERS buy results, not FEATURES!', 'Explain business outcomes before listing specifications.'),
        ('Cash flow keeps a business alive.', 'Keep three reserves for taxes and supplier payments.'),
        ('Hiring begins with a clear role.', 'Define three business skills before interviewing candidates.'),
        ('Price reflects customer value.', 'Test three business prices with a small product group.'),
    ]
    segments = []
    for index, (opening, payoff) in enumerate(pairs):
        start = index * 100
        segments.extend([{'start': start, 'end': start + 10, 'text': opening},
                         {'start': start + 10, 'end': start + 35, 'text': payoff}])
    source = {'segments': segments, 'duration': 1800, 'title': 'Business', 'heatmap': [
        {'start_time': 0, 'end_time': 35, 'value': 1}, {'start_time': 35, 'end_time': 100, 'value': .1},
        {'start_time': 100, 'end_time': 135, 'value': .95}, {'start_time': 135, 'end_time': 1800, 'value': .1}]}
    choices = mod.select_moments(source, 4, 35)
    starts = [item['clip_plan']['start_seconds'] for item in choices]
    assert len(starts) == 4 and sum(start < 135 for start in starts) <= 1
    assert all(item['diversity_note'] for item in choices)


def test_replay_peak_does_not_force_an_advertisement_into_the_batch():
    mod = sections_module()
    pairs = [
        ('Enjoy coffee while running a business at home.', 'Get $30 off your first order at coffee.com slash host.'),
        ('Cash flow keeps a business alive.', 'Keep reserves for taxes and supplier payments.'),
        ('Hiring begins with a clear role.', 'Define three skills before interviewing candidates.'),
        ('Price reflects customer value.', 'Test a price increase with a small product group.'),
        ('Meetings should produce decisions.', 'Assign a responsible owner and deadline to every action.'),
    ]
    segments = []
    for index, (opening, payoff) in enumerate(pairs):
        start = index * 100
        segments.extend([{'start': start, 'end': start + 10, 'text': opening},
                         {'start': start + 10, 'end': start + 35, 'text': payoff}])
    source = {'segments': segments, 'duration': 1800, 'title': 'Business', 'heatmap': [
        {'start_time': 0, 'end_time': 35, 'value': 1}, {'start_time': 35, 'end_time': 1800, 'value': .1}]}
    choices = mod.select_moments(source, 4, 35)
    assert len(choices) == 4
    assert all(choice['clip_plan']['start_seconds'] >= 100 for choice in choices)


def test_section_download_is_bounded_and_rejects_full_length_response(tmp_path, monkeypatch):
    from clipping import media
    mod = sections_module()
    calls = []

    def command(args, **kwargs):
        calls.append(args)
        (tmp_path / 'section.mp4').write_bytes(b'PARTIAL TEST ONLY')
        return ''

    monkeypatch.setattr(media, 'command', command)
    monkeypatch.setattr(media, 'probe', lambda p: {'format': {'duration': '41'}, 'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]})
    source = {'id': 'abcdefghijk', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}
    plan = {'start_seconds': 600, 'duration_seconds': 35, 'aspect_ratio': '9:16'}
    result = mod.download_section(source, plan, 1800, tmp_path)
    args = calls[0]
    value = args[args.index('--download-sections') + 1]
    assert re.fullmatch(r'\*597(?:\.0+)?-638(?:\.0+)?', value)
    assert '--force-keyframes-at-cuts' in args and '--ignore-config' in args
    assert result['source_offset'] == 597 and result['local_start'] == 3
    assert result['path'].is_file()
    monkeypatch.setattr(media, 'probe', lambda p: {'format': {'duration': '1800'}, 'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]})
    with pytest.raises(ValueError, match='section'):
        mod.download_section(source, plan, 1800, tmp_path)


def test_section_cache_reuses_only_hash_valid_bounded_source_windows(tmp_path, monkeypatch):
    from clipping import media
    mod = sections_module()
    calls = []
    cached = {}

    class Cache:
        def get_file(self, kind, identity):
            return cached.get((kind, json.dumps(identity, sort_keys=True)))
        def put_file(self, kind, identity, path, **kwargs):
            cached[(kind, json.dumps(identity, sort_keys=True))] = path

    cache = Cache()
    def download(args, timeout):
        calls.append(args)
        (first_folder / 'section.mp4').write_bytes(b'VALID BOUNDED SECTION')
        return ''

    first_folder = tmp_path / 'first'
    monkeypatch.setattr(mod, 'remote_command', download)
    monkeypatch.setattr(media, 'probe', lambda p: {'format': {'duration': '41'},
        'streams': [{'codec_type': 'video'}, {'codec_type': 'audio'}]})
    source = {'id': 'abcdefghijk', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}
    plan = {'start_seconds': 600, 'duration_seconds': 35}
    original = mod.download_section(source, plan, 1800, first_folder, cache=cache)
    second = mod.download_section(source, plan, 1800, tmp_path / 'second', cache=cache)
    assert len(calls) == 1
    assert second['path'].read_bytes() == original['path'].read_bytes()
    assert second['path'] != original['path']


def test_section_cache_trims_a_verified_containing_section_without_network(tmp_path, monkeypatch):
    from app.repositories.cache import CacheRepository
    from clipping import media
    mod = sections_module()
    cache = CacheRepository(tmp_path / 'cache.db')
    cached = tmp_path / 'wide.mp4'
    media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:r=10',
        '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono', '-t', '40',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(cached)], timeout=30)
    cache.put_file('downloaded_section', {'youtube_video_id': 'abcdefghijk', 'source_offset': 590,
        'requested_end': 630, 'format': 'bounded-audio-video-v1'}, cached, ttl_seconds=3600)
    monkeypatch.setattr(mod, 'remote_command', lambda *args, **kwargs: pytest.fail('should reuse containing cache'))

    result = mod.download_section({'id': 'abcdefghijk', 'url': 'https://youtube.test/video'},
        {'start_seconds': 600, 'duration_seconds': 20}, 1800, tmp_path / 'trimmed', cache=cache)

    assert result['source_offset'] == 597
    assert result['duration'] == pytest.approx(26, abs=1.2)
    assert result['local_start'] == 3
    assert media.probe(result['path'])['streams']
    stats = cache.stats()
    assert stats['requests'] == 1 and stats['hits'] == 1
    assert stats['by_kind']['downloaded_section']['containing_hits'] == 1


@pytest.mark.parametrize('cached_content', ['unreadable', 'short_window'])
def test_resume_replaces_an_invalid_cached_section_with_only_the_requested_window(tmp_path, monkeypatch, cached_content):
    from clipping import media
    mod = sections_module()
    complete = tmp_path / 'complete.mp4'
    folder = tmp_path / 'section'
    folder.mkdir()
    cached = folder / 'section.mp4'

    def make_video(path, duration):
        media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', 'color=c=black:s=64x64:r=1',
            '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono', '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(path)], timeout=30)

    make_video(complete, 21)
    if cached_content == 'unreadable':
        cached.write_bytes(b'INTERRUPTED DOWNLOAD')
    else:
        make_video(cached, 2)
    requests = []

    def download(args, timeout):
        requests.append(args)
        shutil.copyfile(complete, cached)
        return ''

    monkeypatch.setattr(mod, 'remote_command', download)
    source = {'url': 'https://www.youtube.com/watch?v=abcdefghijk'}
    plan = {'start_seconds': 600, 'duration_seconds': 15}
    result = mod.download_section(source, plan, 1800, folder)
    assert result['path'].read_bytes() == complete.read_bytes()
    assert result['source_offset'] == 597 and result['local_start'] == 3
    assert result['duration'] == 21
    assert len(requests) == 1
    args = requests[0]
    assert args[args.index('--download-sections') + 1] == '*597-618'
    mod.download_section(source, plan, 1800, folder)
    assert len(requests) == 1  # A valid recovered section remains a reusable checkpoint.


def test_section_failures_redact_signed_urls_and_never_fall_back_to_full_download(tmp_path, monkeypatch):
    from clipping import media
    mod = sections_module()
    calls = []

    def fail(args, **kwargs):
        calls.append(args)
        raise ValueError('Connection refused https://media.test/?token=SECRET')

    monkeypatch.setattr(media, 'command', fail)
    with pytest.raises(media.SourceUnavailable) as exc:
        mod.download_section({'url': 'https://www.youtube.com/watch?v=abcdefghijk'},
                             {'start_seconds': 10, 'duration_seconds': 35}, 1800, tmp_path)
    assert len(calls) == 1 and '--download-sections' in calls[0]
    assert 'SECRET' not in str(exc.value)


def test_studio_captions_use_selective_timed_emphasis_and_preserve_speech():
    from clipping.caption_styles import ass_for_window
    segments = [{'start': 0, 'end': 3, 'text': 'Trust your people.', 'words': [
        {'start': 0, 'end': 1, 'word': 'Trust'}, {'start': 1, 'end': 2, 'word': ' your'},
        {'start': 2, 'end': 3, 'word': ' people.'}]}]
    result = ass_for_window(segments, 0, 3, 1080, 1920, 'studio')
    rows = [line.split(',', 9)[9] for line in result.splitlines() if line.startswith('Dialogue:')]
    assert any(' '.join(re.sub(r'\{[^}]*\}', '', row).replace(r'\N', ' ').split()) == 'Trust your people.' for row in rows)
    assert 'TRUST YOUR PEOPLE' not in result
    assert 'F6DD55' in result
    assert r'\move' not in result and r'\t(' not in result
    assert r'\1c&HF6DD55&}your' not in result


def production_source(count=5):
    subjects = ['Cash flow protects reserves', 'Hiring needs complementary skills',
                'Customer research reveals demand', 'Meetings should produce decisions',
                'Pricing reflects the outcome', 'Training develops independent judgment']
    return {'title': 'Business decisions', 'duration': 1800, 'segments': [
        {'start': i * 100, 'end': i * 100 + 35,
         'text': subjects[i % len(subjects)] + '. Write a plan before committing resources.'}
        for i in range(count)]}


def test_selection_supports_two_moments_and_twenty_requested_moments():
    mod = sections_module()
    assert len(mod.select_moments(production_source(2), 2, 35)) == 2
    choices = mod.select_moments(production_source(5), 20, 35, strict=True)
    assert len(choices) == 5
    with pytest.raises(ValueError, match='count|twenty|20'):
        mod.select_moments(production_source(), 21, 35)


def test_strict_selection_returns_one_strong_moment_without_requiring_three():
    mod = sections_module()
    source = production_source(1)
    choices = mod.select_moments(source, 4, 35, strict=True)
    assert len(choices) == 1
    with pytest.raises(ValueError, match='three'):
        mod.select_moments(source, 4, 35)


def test_historical_exclusions_reject_interval_reuse_and_repeated_takeaways():
    mod = sections_module()
    source = production_source(5)
    excluded = [
        {'clip_plan': {'start_seconds': 0, 'duration_seconds': 35},
         'source_excerpt': source['segments'][0]['text']},
        {'clip_plan': {'start_seconds': 1300, 'duration_seconds': 35},
         'source_excerpt': source['segments'][1]['text'].upper()},
    ]
    choices = mod.select_moments(source, 4, 35, strict=True, excluded=excluded)
    assert {item['clip_plan']['start_seconds'] for item in choices} == {200, 300, 400}


def test_strict_selection_refuses_the_previous_fifty_cent_greeting_roast():
    mod = sections_module()
    source = {'title': '50 Cent interview', 'duration': 1800, 'segments': [
        {'start': 0, 'end': 10, 'text': "What's up everybody? WELCOME TO FL. OUR GUEST today has three careers."},
        {'start': 10, 'end': 35, 'text': 'Ladies and gentlemen, Curtis 50 Cent Jackson.'},
        {'start': 100, 'end': 135, 'text': 'Music rewards consistency. Finish the record before chasing the next idea.'},
    ]}
    choices = mod.select_moments(source, 4, 35, strict=True)
    assert [item['clip_plan']['start_seconds'] for item in choices] == [100]


def test_historical_text_rejection_does_not_exhaust_the_twenty_candidate_pool():
    mod = sections_module()
    repeated = 'Cash flow protects reserves. Write a plan before committing resources.'
    source = {'title': 'Business', 'duration': 3000, 'segments': [
        {'start': i * 100, 'end': i * 100 + 35, 'text': repeated} for i in range(21)] + [
        {'start': 2500, 'end': 2535, 'text': 'Talent grows through practical feedback. Teach judgment by discussing difficult decisions.'}]}
    excluded = [{'clip_plan': {'start_seconds': 2800, 'duration_seconds': 35}, 'source_excerpt': repeated}]
    choices = mod.select_moments(source, 4, 35, strict=True, excluded=excluded)
    assert [item['clip_plan']['start_seconds'] for item in choices] == [2500]
