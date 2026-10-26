from pathlib import Path

from test_publishing import prepared


AI_INTERVIEW = (
    'Do you see yourself as a risk taker? Yeah, big time. AI is here to stay '
    'and I wanted to have human, have AI, and put it together. People are now '
    'selling their images and using avatars. You get blasted by the creative '
    'community, but it is out of our control.'
)


def test_sports_discovery_label_cannot_route_an_ai_interview_moment_as_sports():
    from clipping.library import niche_routing
    result = niche_routing({'niches': ['Sport']}, excerpt=AI_INTERVIEW)
    assert result['niche'] == 'unclassified'
    assert result['needs_review'] is True
    assert result['basis'] == 'excerpt_discovery_conflict'
    assert result['topic_evidence'][0]['topic'] == 'artificial_intelligence'
    assert result['discovery_niches'] == ['sports']


def test_film_career_moment_from_sports_source_requires_niche_review():
    from clipping.library import niche_routing
    result = niche_routing({'niches': ['Sports']}, excerpt=(
        'My acting career began with auditions. In the film industry, '
        'you need to keep making work even when the roles disappear.'))
    assert result['niche'] == 'unclassified' and result['needs_review']
    assert result['basis'] == 'excerpt_discovery_conflict'


def test_sports_moment_can_support_its_discovery_niche_without_claiming_semantic_certainty():
    from clipping.library import niche_routing
    result = niche_routing({'niches': ['Sport']}, excerpt=(
        'In the Champions League a penalty kick can decide the match. '
        'The goalkeeper watches the hips before committing.'))
    assert result['niche'] == 'sports'
    assert result['basis'] == 'excerpt_supported_discovery'
    assert result['needs_review'] is False


def test_generic_or_missing_moment_evidence_abstains_in_new_routing():
    from clipping.library import niche_routing
    for excerpt in ('', 'The team should train and model the game before the next step.'):
        result = niche_routing({'niches': ['Sport']}, excerpt=excerpt)
        assert result['niche'] == 'unclassified' and result['needs_review']
        assert result['topic_evidence'] == []
    result = niche_routing({'niches': ['Sports', 'Business']}, excerpt=AI_INTERVIEW)
    assert result['niche'] == 'unclassified' and result['needs_review']


def test_explicit_preference_is_preserved_but_conflicting_moment_is_flagged():
    from clipping.library import niche_routing
    result = niche_routing({'niches': ['Sport']}, 'sports', excerpt=AI_INTERVIEW)
    assert result['niche'] == result['requested_niche'] == 'sports'
    assert result['basis'] == 'user_selected'
    assert result['needs_review'] is True
    assert result['review_reasons'] == ['excerpt_discovery_conflict']


def test_explicit_per_clip_editorial_review_can_override_source_and_batch_preference(tmp_path):
    from clipping.library import niche_folder, niche_routing
    result = niche_routing({'niches': ['Sport']}, 'sports', excerpt=AI_INTERVIEW,
        review={'niche': 'ai-technology', 'rationale': 'Reviewed the actual AI and avatar discussion.'})
    assert result['niche'] == 'ai-technology' and not result['needs_review']
    assert result['basis'] == 'editorial_review'
    assert result['requested_niche'] == 'sports'
    assert result['review_rationale'] == 'Reviewed the actual AI and avatar discussion.'
    assert niche_folder(tmp_path, result['niche']) == tmp_path / 'ai-technology'


def test_invalid_editorial_review_fails_before_it_can_choose_a_folder():
    import pytest
    from clipping.library import niche_routing
    for review in ({}, {'niche': '../../outside', 'rationale': 'Reviewed'},
                   {'niche': 'unclassified', 'rationale': 'Reviewed'},
                   {'niche': 'sports', 'rationale': '  '}, {'niche': 'sports', 'rationale': 123}):
        with pytest.raises(ValueError, match='niche review'):
            niche_routing({'niches': ['Sports']}, excerpt=AI_INTERVIEW, review=review)


def test_library_exposes_saved_routing_evidence_without_reclassifying_historical_clips(tmp_path):
    from clipping.library import niche_library
    store, _, _ = prepared(tmp_path)
    clip = store.get_clip('clip')
    routing = {'niche': 'ai-technology', 'basis': 'editorial_review', 'needs_review': False,
               'review_rationale': 'Reviewed AI discussion.'}
    store.save_clip(clip | {'settings': {'delivery_niche': 'ai-technology', 'niche_routing': routing}})
    category = next(item for item in niche_library(store, root=tmp_path)['categories']
                    if item['id'] == 'ai-technology')
    assert category['clips'][0]['routing_basis'] == 'editorial_review'
    assert category['clips'][0]['niche_routing'] == routing
    store.save_clip(clip | {'settings': {'delivery_niche': 'sports', 'source': {'niches': ['Sport']},
                                       'transcript': AI_INTERVIEW}})
    category = next(item for item in niche_library(store, root=tmp_path)['categories']
                    if item['id'] == 'sports')
    assert category['clips'][0]['niche'] == 'sports'
    assert store.get_clip('clip')['path'] == clip['path']


def test_delivery_routes_the_actual_moment_and_persists_the_review_reason(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from clipping import batch
    store, _, video = prepared(tmp_path)
    subtitles = video.with_suffix('.srt')
    subtitles.write_text('source backed captions')
    state = {'id': store.get_clip('clip')['order_id'], 'source_selection': {'id': 'source', 'niches': ['Sport']}}
    controller = SimpleNamespace(store=store, state=state, folder=tmp_path,
        config=SimpleNamespace(niche=None, organize_by_niche=True, caption_style='studio',
                               caption_styles=None, framing_mode='fit'),
        engine=SimpleNamespace(artifact=lambda identifier, name: video if name == 'clip' else subtitles),
        update=lambda **values: state.update(values))
    monkeypatch.setattr(batch.orchestrator, 'verify_export', lambda *args: {'checks': {}})
    plan = {'start_seconds': 798.48, 'duration_seconds': 50.159}
    entry = {'number': 1, 'local_clip_plan': plan, 'source_clip_plan': plan,
             'source_offset': 0, 'post_caption': 'Private AI discussion.'}
    output = tmp_path / 'delivered'
    output.mkdir()
    batch.deliver_clip(controller, {'id': 'clip', 'payload': {}, 'output': {}}, entry,
                       {'source_excerpt': AI_INTERVIEW, 'note': 'Editorial selection.'}, output)
    result = state['batch_results'][0]
    assert Path(result['clip']).parent == output / 'unclassified'
    assert result['niche_routing']['basis'] == 'excerpt_discovery_conflict'
    assert store.get_clip('clip')['settings']['niche_routing'] == result['niche_routing']
    entry['niche_review'] = {'niche': 'ai-technology', 'rationale': 'Reviewed this AI discussion.'}
    batch.deliver_clip(controller, {'id': 'clip', 'payload': {}, 'output': {}}, entry,
                       {'source_excerpt': AI_INTERVIEW, 'note': 'Editorial selection.'}, output)
    reviewed = state['batch_results'][-1]
    assert Path(reviewed['clip']).parent == output / 'ai-technology'
    assert reviewed['niche_routing']['basis'] == 'editorial_review'
    del entry['niche_review']
    batch.deliver_clip(controller, {'id': 'clip', 'payload': {}, 'output': {}}, entry,
                       {'source_excerpt': 'A Champions League penalty kick.', 'note': 'Editorial selection.'}, output)
    assert state['batch_results'][-1]['niche_routing'] == reviewed['niche_routing']
    assert store.get_clip('clip')['settings']['delivery_niche'] == 'ai-technology'


def test_niche_routing_uses_recorded_categories_without_guessing(tmp_path):
    from clipping.library import route_niche, niche_folder
    assert route_niche({'niches': ['Sport']}) == 'sports'
    assert route_niche({'niches': ['Streams']}) == 'streams'
    assert route_niche({'niches': ['Business', 'Education']}) == 'unclassified'
    assert route_niche({'niches': ['Business', 'Education']}, 'Education') == 'education'
    assert route_niche({'niches': ['../../escape']}) == 'unclassified'
    assert niche_folder(tmp_path, 'sports') == tmp_path / 'sports'
    assert niche_folder(tmp_path, '../../escape') == tmp_path / 'unclassified'


def test_explicit_canonical_niche_slug_wins_over_discovery_labels():
    from clipping.library import IDS, route_niche
    for slug in IDS:
        assert route_niche({'niches': ['Business']}, slug) == slug
        assert route_niche({'niches': [slug]}) == slug


def test_library_distinguishes_saved_records_from_available_exports(tmp_path):
    from clipping.library import niche_library
    store, _, _ = prepared(tmp_path)
    clip = store.get_clip('clip')
    video = tmp_path / 'sports' / 'clip.mp4'
    video.parent.mkdir()
    video.write_bytes(b'fixture')
    subs = video.with_suffix('.srt')
    subs.write_text('fixture subtitles')
    from clipping.media import file_hash
    store.save_clip(clip | {'path': str(video), 'subtitles': str(subs),
        'sha256': file_hash(video),
        'settings': {'delivery_niche': 'sports', 'niche': 'Sport'}})
    report = niche_library(store, root=tmp_path)
    sports = next(item for item in report['categories'] if item['id'] == 'sports')
    assert sports['clip_count'] == 1 and sports['available_clip_count'] == 0
    assert sports['clips'][0]['missing_artifacts'] == ['post_caption']
    video.with_name('clip-caption.txt').write_text('A separate post caption')
    sports = next(item for item in niche_library(store, root=tmp_path)['categories'] if item['id'] == 'sports')
    assert sports['available_clip_count'] == 1
    assert sports['clips'][0]['available'] is True
    assert report['publishing_enabled'] is False
    assert all(Path(item['folder']).parent == tmp_path for item in report['categories'])


def test_library_rejects_truncated_or_replaced_exports(tmp_path):
    from clipping.library import delivery_availability
    from clipping.media import file_hash
    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'original export')
    subtitles = video.with_suffix('.srt')
    subtitles.write_text('actual subtitles')
    video.with_name('clip-caption.txt').write_text('post caption')
    hashes = {'video': file_hash(video)}
    video.write_bytes(b'changed export')
    result = delivery_availability(video, subtitles, expected_hashes=hashes)
    assert not result['available'] and result['changed_artifacts'] == ['video']
    subtitles.write_text('')
    assert delivery_availability(video, subtitles)['missing_artifacts'] == ['subtitles']


def test_library_prefers_verified_niche_copy_without_rewriting_saved_paths(tmp_path):
    import shutil
    from clipping.library import niche_library
    from clipping.media import file_hash
    store, _, original = prepared(tmp_path)
    subtitle = original.with_suffix('.srt')
    subtitle.write_text('source backed subtitles')
    caption = original.with_name(original.stem + '-caption.txt')
    caption.write_text('post caption')
    record = store.get_clip('clip')
    store.save_clip(record | {'subtitles': str(subtitle), 'settings': {'delivery_niche': 'business',
        'delivery_hashes': {'video': file_hash(original), 'subtitles': file_hash(subtitle),
                            'post_caption': file_hash(caption)}}})
    folder = tmp_path / 'business'
    folder.mkdir()
    for path in (original, subtitle, caption):
        shutil.copyfile(path, folder / path.name)
    item = next(category for category in niche_library(store, root=tmp_path)['categories']
                if category['id'] == 'business')['clips'][0]
    assert item['path'] == str(folder / original.name)
    assert item['original_path'] == store.get_clip('clip')['path'] == str(original)
    assert item['verified_artifacts'] == ['video', 'subtitles', 'post_caption']
    (folder / subtitle.name).write_text('changed subtitles')
    item = next(category for category in niche_library(store, root=tmp_path)['categories']
                if category['id'] == 'business')['clips'][0]
    assert item['path'] == str(original)


def test_niche_and_caption_links_cannot_redirect_writes(tmp_path):
    import pytest
    from clipping.library import niche_folder
    from clipping.batch import write_caption
    root, outside = tmp_path / 'clips', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    try:
        (root / 'business').symlink_to(outside, target_is_directory=True)
        (root / 'caption.txt').symlink_to(outside / 'protected.txt')
    except OSError:
        pytest.skip('Symbolic link creation is unavailable in this Windows account')
    with pytest.raises(ValueError, match='delivery root'):
        niche_folder(root, 'business')
    with pytest.raises(ValueError, match='symbolic links'):
        write_caption(root / 'caption.txt', 'not allowed')
    assert not (outside / 'protected.txt').exists()
