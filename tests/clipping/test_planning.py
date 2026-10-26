import importlib
import json
import random
import re
from pathlib import Path

import pytest


def module():
    return importlib.import_module('clipping.planning')


def segments():
    return [{'start': i * 10, 'end': (i + 1) * 10, 'text': text} for i, text in enumerate([
        'Welcome to this software demonstration.', 'Why does this AI tool fail?',
        'Here are three steps to check the result.', 'Now the output matches the source.',
        'Review the result before sharing it.', 'That completes the demonstration.',
    ])]


def test_planner_returns_bounded_distinct_source_windows_with_explanations():
    result = module().suggest_cuts(segments(), 60, target_duration=30,
                                  min_duration=20, max_duration=35, keywords='AI')
    assert 1 <= len(result) <= 3
    for item in result:
        plan = item['clip_plan']
        assert plan['start_seconds'] in {segment['start'] for segment in segments()}
        assert 20 <= plan['duration_seconds'] <= 35
        assert plan['start_seconds'] + plan['duration_seconds'] <= 60
        assert item['reasons'] and item['source_excerpt'] and item['caption']
        assert item['score_type'] == 'editorial_heuristic'
        assert 'probability' not in item
    assert len({json.dumps(item['clip_plan'], sort_keys=True) for item in result}) == len(result)


def test_planner_rejects_invalid_boundaries_and_insufficient_speech():
    with pytest.raises(ValueError, match='duration'):
        module().suggest_cuts(segments(), 60, min_duration=40, max_duration=20)
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 2, 'text': 'Hello.'}], 2,
                              min_duration=10, max_duration=20)
    with pytest.raises(ValueError, match='Transcript'):
        module().suggest_cuts([], 60)


def test_filler_question_is_not_scored_as_a_useful_opening_hook():
    transcript = [
        {'start': 0, 'end': 10, 'text': 'You know what I mean?'},
        {'start': 10, 'end': 30, 'text': 'My business has three people who can keep up.'},
        {'start': 30, 'end': 40, 'text': 'Why does hiring change a business?'},
        {'start': 40, 'end': 60, 'text': 'These three people explain the results.'},
    ]
    result = module().suggest_cuts(transcript, 60, min_duration=30, max_duration=30,
                                  keywords='business')
    assert result[0]['clip_plan']['start_seconds'] == 30
    assert result[0]['caption'] == 'Why does hiring change a business?'


def test_prefixed_filler_loses_to_the_same_point_opened_directly():
    transcript = [
        {'start': 0, 'end': 10, 'text': 'You know, our business needs three skilled people.'},
        {'start': 10, 'end': 35, 'text': 'Clear roles make a team effective.'},
        {'start': 100, 'end': 110, 'text': 'A business needs three skilled people.'},
        {'start': 110, 'end': 135, 'text': 'Clear roles make a team effective.'},
    ]
    best = module().suggest_cuts(transcript, 180, target_duration=35,
                                min_duration=35, max_duration=35, keywords='business,people')[0]
    assert best['clip_plan']['start_seconds'] == 100


def test_a_long_speech_gap_loses_to_a_continuous_complete_moment():
    transcript = [
        {'start': 0, 'end': 3, 'text': 'Why does a business need a clear plan?'},
        {'start': 26, 'end': 35, 'text': 'Three steps keep the business moving.'},
        {'start': 100, 'end': 110, 'text': 'Why does a business need a clear plan?'},
        {'start': 110, 'end': 135, 'text': 'Three steps keep the business moving.'},
    ]
    choices = module().suggest_cuts(transcript, 180, target_duration=35,
                                   min_duration=35, max_duration=35, keywords='business')
    assert choices[0]['clip_plan']['start_seconds'] == 100
    sparse = next(item for item in choices if item['clip_plan']['start_seconds'] == 0)
    assert sparse['quality']['silence_seconds'] == 23
    assert sparse['quality']['largest_speech_gap'] == 23


def test_discount_offer_is_flagged_even_without_the_word_sponsor():
    transcript = [
        {'start': 0, 'end': 10, 'text': 'Make great coffee at home for your business.'},
        {'start': 10, 'end': 35, 'text': 'Get $30 off your first order at coffee.com slash host.'},
        {'start': 100, 'end': 110, 'text': 'A home business needs clear working hours.'},
        {'start': 110, 'end': 135, 'text': 'Set three boundaries so your team can solve problems.'},
    ]
    choices = module().suggest_cuts(transcript, 180, target_duration=35,
                                   min_duration=35, max_duration=35, keywords='home,business')
    assert choices[0]['clip_plan']['start_seconds'] == 100
    advertisement = next(item for item in choices if item['clip_plan']['start_seconds'] == 0)
    assert advertisement['quality']['promotional'] is True


def test_question_with_an_unseen_referent_is_not_rewarded_as_a_standalone_hook():
    transcript = [
        {'start': 0, 'end': 10, 'text': 'Did you ever understand him?'},
        {'start': 10, 'end': 35, 'text': 'Our business needed three skilled people.'},
        {'start': 100, 'end': 110, 'text': 'Why does a business need skilled people?'},
        {'start': 110, 'end': 135, 'text': 'Three complementary skills solve the problem.'},
    ]
    choices = module().suggest_cuts(transcript, 180, target_duration=35,
                                   min_duration=35, max_duration=35, keywords='business')
    assert choices[0]['clip_plan']['start_seconds'] == 100
    referential = next(item for item in choices if item['clip_plan']['start_seconds'] == 0)
    assert referential['quality']['context_dependent_opening'] is True


def test_planner_avoids_starting_in_the_middle_of_an_unfinished_sentence():
    transcript = [
        {'start': 0, 'end': 10, 'text': 'We explain the process and'},
        {'start': 10, 'end': 20, 'text': 'why do three AI tools fail?'},
        {'start': 20, 'end': 30, 'text': 'Here is the fix.'},
        {'start': 30, 'end': 40, 'text': 'Why does an AI tool fail?'},
        {'start': 40, 'end': 60, 'text': 'Three checks solve the problem.'},
    ]
    best = module().suggest_cuts(transcript, 60, min_duration=30, max_duration=30, keywords='AI')[0]
    assert best['clip_plan']['start_seconds'] == 30


def test_planner_keeps_an_answer_after_the_opening_question_when_it_fits():
    transcript = [
        {'start': 0, 'end': 10, 'text': 'Why does a business fail?'},
        {'start': 10, 'end': 30, 'text': 'What do you do when a team cannot keep up?'},
        {'start': 30, 'end': 39, 'text': 'Build a team with three complementary skills.'},
    ]
    best = module().suggest_cuts(transcript, 39, min_duration=20, max_duration=45, keywords='business')[0]
    assert best['clip_plan']['start_seconds'] == 0
    assert best['clip_plan']['duration_seconds'] == 39


def test_multiple_topic_matches_beat_a_generic_question_from_the_same_niche():
    transcript = [
        {'start': 0, 'end': 10, 'text': 'Why did we hire three people?'},
        {'start': 10, 'end': 30, 'text': 'Our business team is busy.'},
        {'start': 30, 'end': 40, 'text': 'Working from home is impossible for this business.'},
        {'start': 40, 'end': 60, 'text': 'An office brings people together and sparks ideas.'},
    ]
    best = module().suggest_cuts(transcript, 60, min_duration=30, max_duration=30,
                                  keywords='business,home,impossible,office')[0]
    assert best['clip_plan']['start_seconds'] == 30


def test_source_title_matching_ignores_common_pronouns_and_auxiliary_verbs(tmp_path):
    transcript = [
        {'start': 0, 'end': 10, 'text': 'Can you understand him?'},
        {'start': 10, 'end': 30, 'text': "You can raise one child or two and it's very different."},
        {'start': 30, 'end': 40, 'text': 'Build a business from home.'},
        {'start': 40, 'end': 60, 'text': 'An impossible office policy stops remote teams.'},
    ]
    (tmp_path / 'transcript.json').write_text(json.dumps({'segments': transcript}))
    data = {'campaign': {'duration_min': 30, 'duration_max': 30}, 'research_keywords': 'business',
            'clip_plan': {'duration_seconds': 30, 'aspect_ratio': '9:16'}}
    output = {'transcript_path': 'transcript.json', 'source_duration': 60,
              'source_selection': {'title': "Can You Build A Business From Home? It's Impossible!"}}
    result = module().prepare_clip_plan(data, output, tmp_path, tmp_path)
    assert result['selected_clip_plan']['start_seconds'] == 30


def test_replay_peak_beats_a_generic_hook_but_keeps_real_transcript_boundaries():
    heatmap = [{'start_time': 0, 'end_time': 40, 'value': .1},
               {'start_time': 40, 'end_time': 50, 'value': 1},
               {'start_time': 50, 'end_time': 60, 'value': .2}]
    result = module().suggest_cuts(segments(), 60, target_duration=20,
                                  min_duration=20, max_duration=20, heatmap=heatmap)
    best = result[0]
    start = best['clip_plan']['start_seconds']
    assert start <= 45 < start + best['clip_plan']['duration_seconds']
    assert best['score_type'] == 'youtube_replay_heatmap'
    assert 'Review the result' in best['source_excerpt']
    assert 'replay' in ' '.join(best['reasons']).lower()


@pytest.mark.parametrize('heatmap', [None, [], [{'start_time': 0, 'end_time': 60, 'value': .5}],
    [{'start_time': 0, 'end_time': 70, 'value': 1}],
    [{'start_time': 0, 'end_time': 30, 'value': float('nan')}],
    [{'start_time': 0, 'end_time': 30, 'value': True}]])
def test_missing_flat_or_invalid_replay_data_stays_an_editorial_suggestion(heatmap):
    result = module().suggest_cuts(segments(), 60, heatmap=heatmap)
    assert result[0]['score_type'] == 'editorial_heuristic'
    assert 'replay_score' not in result[0]


def test_automatic_planner_refuses_overlapping_subtitles():
    with pytest.raises(ValueError, match='overlap'):
        module().suggest_cuts([{'start': 0, 'end': 40, 'text': 'A full sentence.'},
                              {'start': 10, 'end': 20, 'text': 'A different sentence.'}], 40)


@pytest.mark.parametrize('ending', ['check the output.', 'check the output."', 'check the output!”',
                                  '检查结果。」'])
def test_planner_uses_a_nearby_sentence_ending_instead_of_cutting_it_short(ending):
    transcript = [{'start': 0, 'end': 10, 'text': 'Why does this AI result fail?'},
                  {'start': 10, 'end': 30, 'text': 'Here are three steps to repair it and'},
                  {'start': 30, 'end': 34, 'text': ending}]
    result = module().suggest_cuts(transcript, 34, target_duration=30,
                                  min_duration=20, max_duration=35, keywords='AI')
    assert result[0]['clip_plan'] == {'start_seconds': 0, 'duration_seconds': 34, 'aspect_ratio': '9:16'}
    assert ending in result[0]['source_excerpt']


def test_planner_prefers_sentence_endings_over_an_unfinished_high_scoring_hook():
    transcript = [{'start': 0, 'end': 20, 'text': 'A complete explanation ends here.'},
                  {'start': 20, 'end': 40, 'text': 'Why do three AI results fail and'}]
    result = module().suggest_cuts(transcript, 40, target_duration=30,
                                  min_duration=20, max_duration=30, keywords='AI')
    assert result[0]['clip_plan']['start_seconds'] == 0
    assert result[0]['clip_plan']['duration_seconds'] == 20


def test_unpunctuated_transcript_uses_bounded_fallback_with_context_warning():
    transcript = [{'start': 0, 'end': 10, 'text': 'why is the output different'},
                  {'start': 10, 'end': 30, 'text': 'three checks explain the results'}]
    result = module().suggest_cuts(transcript, 30, target_duration=30,
                                  min_duration=20, max_duration=30)
    assert result[0]['clip_plan']['duration_seconds'] == 30
    assert any('sentence ending' in reason.lower() and 'review' in reason.lower()
               for reason in result[0]['reasons'])


def test_sentence_ending_cannot_extend_a_clip_beyond_the_campaign_limit():
    transcript = [{'start': 0, 'end': 10, 'text': 'Why does the output fail?'},
                  {'start': 10, 'end': 30, 'text': 'Three steps fix it and'},
                  {'start': 30, 'end': 34, 'text': 'finish the check.'}]
    result = module().suggest_cuts(transcript, 34, target_duration=30,
                                  min_duration=25, max_duration=32)
    assert result[0]['clip_plan']['duration_seconds'] == 30
    assert all(item['clip_plan']['duration_seconds'] <= 32 for item in result)


@pytest.mark.parametrize('url', ['https://youtube.com/playlist?list=test',
    'https://youtube.com/watch', 'https://youtube.com.evil.test/watch?v=abcdefghijk',
    'https://user:pass@youtube.com/watch?v=abcdefghijk',
    'https://youtube.com:8443/watch?v=abcdefghijk', 'http://youtu.be/abcdefghijk'])
def test_youtube_source_rejects_nonvideo_or_unsafe_urls(url):
    with pytest.raises(ValueError, match='YouTube'):
        module().youtube_url(url)


def test_youtube_source_is_canonical_and_metadata_does_not_download(monkeypatch):
    from clipping import media
    called = []
    def lookup(args, **kwargs):
        called.append(args)
        return json.dumps({'id': 'abcdefghijk', 'title': 'Authorized demo', 'duration': 60,
                           'uploader': 'Example creator', 'formats': [{'url': 'private signed URL'}]})
    monkeypatch.setattr(media, 'command', lookup)
    result = module().inspect_youtube('https://youtu.be/abcdefghijk?t=12')
    assert result['url'] == 'https://www.youtube.com/watch?v=abcdefghijk'
    assert result['duration'] == 60
    assert '--skip-download' in called[0] and '--ignore-config' in called[0]
    assert 'formats' not in result


def test_downloader_prefers_installed_python_module(monkeypatch):
    import sys
    from clipping import media
    monkeypatch.setattr(media.shutil, 'which', lambda name: None)
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name: object())
    assert media.ytdlp_command() == [sys.executable, '-m', 'yt_dlp']
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name: None)
    assert media.ytdlp_command() == ['yt-dlp']


def test_downloader_enables_the_installed_youtube_javascript_runtime(monkeypatch):
    from clipping import media
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name: object())
    monkeypatch.setattr(media.shutil, 'which', lambda name: 'node.exe' if name == 'node' else None)
    assert media.ytdlp_command()[-2:] == ['--js-runtimes', 'node']


def test_automatic_planning_respects_approval_and_persists_selected_cut(tmp_path, monkeypatch):
    from clipping.workflow import ClippingWorkflow
    from clipping import media
    folder = tmp_path
    engine = ClippingWorkflow(folder / 'jobs.db', folder / 'storage')
    data = {'campaign': {'title': 'Demo', 'url': 'https://example.com/campaign', 'platform': 'tiktok',
                        'rights_notes': 'Authorized fixture', 'rules': 'Complete moments',
                        'duration_min': 20, 'duration_max': 35},
            'dry_run': True, 'auto_clip': True, 'research_keywords': 'AI',
            'clip_plan': {'duration_seconds': 30}}
    job = engine.create(data)
    assert not engine.consume_once()
    assert not (engine.storage / 'jobs').exists()
    def ingest(*args):
        return {'source_path': 'fixture.mp4', 'source_duration': 60}
    def transcribe(data, output, target, storage):
        (target / 'transcript.json').write_text(json.dumps({'segments': segments()}), encoding='utf-8')
        return {'transcript_path': (target / 'transcript.json').relative_to(storage).as_posix()}
    rendered = []
    def render(data, output, *args):
        rendered.append(output.get('selected_clip_plan'))
        return {'clip_path': 'fixture-result.mp4', 'clip_sha256': 'fixture-hash'}
    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(media, 'transcribe', transcribe)
    monkeypatch.setattr(media, 'render', render)
    engine.approve(job['id'], job['waiting_step'], job['approval_fingerprint'], True)
    engine.consume_once()
    result = engine.get(job['id'])
    assert result['status'] == 'awaiting_clip_approval', result
    assert result['output']['clip_suggestions']
    assert rendered[0] == result['output']['selected_clip_plan']
    reloaded = ClippingWorkflow(folder / 'jobs.db', folder / 'storage').get(job['id'])
    assert reloaded['output']['selected_clip_plan'] == rendered[0]
    assert 'publication' not in reloaded['output']


def test_automatic_practice_source_fits_the_maximum_clip_window(tmp_path, monkeypatch):
    from clipping import media
    folder = tmp_path
    recorded = []
    def create_source(args, **kwargs):
        recorded.append(float(args[args.index('-t') + 1]))
        Path(args[-1]).write_bytes(b'synthetic source fixture')
    monkeypatch.setattr(media, 'command', create_source)
    monkeypatch.setattr(media, 'probe', lambda path: {'format': {'duration': recorded[-1]}})
    data = {'dry_run': True, 'auto_clip': True,
            'clip_plan': {'start_seconds': 0, 'duration_seconds': 180}}
    result = media.ingest(data, {}, folder, folder)
    assert result['source_duration'] == 180


def test_default_planning_controls_preserve_existing_job_identity(tmp_path):
    from clipping.workflow import ClippingWorkflow
    folder = tmp_path
    engine = ClippingWorkflow(folder / 'jobs.db', folder / 'storage')
    data = {'campaign': {'title': 'Demo', 'url': 'https://example.com/campaign', 'platform': 'tiktok',
                        'rights_notes': 'Synthetic fixture', 'rules': 'Manual cut'}, 'dry_run': True}
    original = engine.create(data, 'same-manual-job')
    repeated = engine.create(data | {'auto_clip': False, 'research_keywords': ''}, 'same-manual-job')
    assert repeated['id'] == original['id']


def test_production_normalizes_dialogue_markers_and_refuses_filler_openings():
    transcript = [
        {'start': 0, 'end': 35, 'text': '>> [laughter] Okay, our business has three skilled people.'},
        {'start': 100, 'end': 135, 'text': '>> A business needs three complementary skills.'},
    ]
    choices = module().suggest_cuts(transcript, 180, min_duration=35, max_duration=35,
                                   require_standalone=True)
    assert [item['clip_plan']['start_seconds'] for item in choices] == [100]
    assert choices[0]['source_excerpt'].startswith('>> A business')
    assert '>>' not in choices[0]['caption']


@pytest.mark.parametrize('opening', [
    "What's up everybody? WELCOME TO FL. OUR GUEST today has three businesses.",
    '>> [applause] Ladies and gentlemen, welcome our guest.',
    'Thanks for watching and subscribe to our channel.',
    'So the third option solved the problem.',
    'Which one did you prefer?',
])
def test_production_rejects_greetings_outros_and_context_dependent_hooks(opening):
    transcript = [{'start': 0, 'end': 35, 'text': opening}]
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts(transcript, 35, min_duration=35, max_duration=35,
                              require_standalone=True)


@pytest.mark.parametrize('ending', ['The reason is that', 'What should a business do?'])
def test_production_requires_a_completed_nonquestion_payoff(ending):
    transcript = [{'start': 0, 'end': 10, 'text': 'A business needs a clear plan.'},
                  {'start': 10, 'end': 35, 'text': ending}]
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts(transcript, 35, min_duration=35, max_duration=35,
                              require_standalone=True)


def test_production_refuses_starting_after_an_unfinished_source_sentence():
    transcript = [{'start': 0, 'end': 10, 'text': 'We explain the process and'},
                  {'start': 10, 'end': 45, 'text': 'three checks solve every problem.'}]
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts(transcript, 45, min_duration=35, max_duration=35,
                              require_standalone=True)


def test_historical_intervals_are_filtered_before_the_final_suggestion_limit():
    transcript = [{'start': i * 100, 'end': i * 100 + 35,
                   'text': 'A clear plan prevents three common mistakes.'} for i in range(24)]
    excluded = [{'start_seconds': i * 100, 'duration_seconds': 35} for i in range(23)]
    choices = module().suggest_cuts(transcript, 2400, min_duration=35, max_duration=35,
                                   excluded_windows=excluded, min_gap=3, limit=1)
    assert choices[0]['clip_plan']['start_seconds'] == 2300


def test_post_caption_removes_dialogue_markers_and_keeps_only_complete_short_sentences():
    value = module().post_caption('>> [laughter] A clear plan protects your time. >> Pick one priority. An unfinished thought and')
    assert value == 'A clear plan protects your time. Pick one priority.'
    assert len(value) <= 220


def test_post_caption_does_not_cut_a_long_sentence_in_half():
    value = module().post_caption('An unusually ' + 'long ' * 70 + 'sentence. A useful complete point.')
    assert value == 'A useful complete point.'
    fallback = module().post_caption('unpunctuated ' * 100)
    assert len(fallback) <= 220 and module().sentence_ending(fallback)


@pytest.mark.parametrize('text', [
    'All right, guys. Take a break for a second. On October 16th, The King returns.',
    'October 16th, Friday, Street Fighter is in theaters around the world. Take your family.',
    'The Paramount Plus hit series returns this season. Stream it now on Paramount Plus.',
    'That did not happen. A different conversation explains the whole situation.',
    "That didn't happen. A different conversation explains the whole situation.",
    'All right, we got to get out of here before we leave. Street Fighter October 16th.',
])
def test_production_rejects_real_interview_ad_breaks_and_unseen_context(text):
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
            min_duration=35, max_duration=35, require_standalone=True)


@pytest.mark.parametrize('text', [
    'What you mean? No. People misunderstood the argument.',
    'Like that. The old version was very different.',
    'Okay. Speaking of movies, people have questions about the training.',
    'All right. Tell me about the film and being an actor.',
])
def test_production_rejects_short_filler_sentences_before_a_later_point(text):
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
            min_duration=35, max_duration=35, require_standalone=True)


def test_production_does_not_treat_a_final_acknowledgment_as_the_payoff():
    transcript = [{'start': 0, 'end': 15, 'text': 'A business needs a clear plan.'},
                  {'start': 15, 'end': 30, 'text': 'Three complementary skills solve the problem.'},
                  {'start': 30, 'end': 35, 'text': '>> Mhm.'}]
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts(transcript, 35, min_duration=35, max_duration=35,
                              require_standalone=True)


def test_strict_selection_rejects_sponsor_acknowledgment_without_a_discount_code():
    text = ('Visit bluechw.com for more details and important safety information. '
            'We thank Blue Chu for sponsoring the pod and the bedroom. Real sports are back.')
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
            min_duration=35, max_duration=35, require_standalone=True)


def test_post_caption_does_not_drop_the_start_of_a_sentence_containing_a_domain():
    text = 'The example.com project failed because its team ignored feedback. Listen before building.'
    assert module().post_caption(text) == text


@pytest.mark.parametrize('text', [
    'Yes, sir. I agree. We should do a fight at the White House.',
    "Dana, we have a closing tradition in this podcast where the last guest leaves a question for the next. My goal is to build a great brand.",
    "Dana, thank you so much for being so generous with your time. I can't wait. Me too.",
    "You've got a very atypical drive in you. My line of questioning is just to understand how that comes to be the case.",
    "I believed I could be successful when I was younger, but let me tell you what.",
    "Why? Well, maybe he just wanted to fight. Frank Warren is a real guy.",
    "One of those moments reminds me of my dad. He showed up drunk to take us to the movies.",
])
def test_production_rejects_actual_cached_interview_weak_windows(text):
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
            min_duration=35, max_duration=35, require_standalone=True)


def test_production_can_extend_a_host_question_to_include_the_complete_answer():
    transcript = [
        {'start': 0, 'end': 15, 'text': 'What makes a team successful? I want to understand what brings people together.'},
        {'start': 15, 'end': 35, 'text': 'Clear roles and complementary skills help people make better decisions.'},
    ]
    result = module().suggest_cuts(transcript, 35, target_duration=15,
        min_duration=15, max_duration=35, require_standalone=True)
    assert result[0]['clip_plan']['start_seconds'] == 0
    assert result[0]['clip_plan']['duration_seconds'] == 35
    assert 'complementary skills' in result[0]['source_excerpt']


@pytest.mark.parametrize('text', [
    "You've got a very atypical drive in you. So my line of questioning isn't really to psychoanalyze. It's really just to understand like how that comes to be the case.",
    "Did you know? I don't know the answer to that. I never liked working for other people.",
    "I think I'm going to do this and she's the one to deal with. A clear plan makes a difference.",
])
def test_production_rejects_complete_actual_host_setup_and_unnamed_context(text):
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
            min_duration=35, max_duration=35, require_standalone=True)


def test_production_recognizes_host_setup_across_public_caption_cue_boundaries():
    transcript = [
        {'start': 0, 'end': 10, 'text': "You've got a very atypical drive. My line of questioning isn't to psychoanalyze. It's really"},
        {'start': 10, 'end': 35, 'text': 'just to understand like how that comes to be the case.'},
    ]
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts(transcript, 35, min_duration=35, max_duration=35,
                              require_standalone=True)


def test_production_rejects_a_question_whose_unknown_subject_is_that():
    transcript = [{'start': 0, 'end': 35, 'text': 'What does that come from? I never liked working for other people.'}]
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts(transcript, 35, min_duration=35, max_duration=35,
                              require_standalone=True)


def test_production_cannot_fix_a_host_meta_setup_by_appending_another_host_guess():
    text = ("There's a certain relentlessness that I've seen in Dana White. "
            "My line of questioning isn't to psychoanalyze. It's to understand how that comes to be the case. "
            "One would guess that there's some kind of chip on your shoulder to some degree.")
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
            min_duration=35, max_duration=35, require_standalone=True)


@pytest.mark.parametrize('text', [
    'Here is a strange fact. About 58% of people watching are not subscribed. I want you to subscribe and hit the subscribe button.',
    'They both had tune up fights. The next boxing match will be a very different challenge.',
    "I was not. And I didn't have a car. I took the bus to my first job.",
])
def test_production_rejects_detected_channel_cta_and_incomplete_pronoun_acknowledgment(text):
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
            min_duration=35, max_duration=35, require_standalone=True)


def test_a_conversational_explanation_of_subscriptions_is_not_a_channel_promotion():
    text = ('Businesses subscribe to a service when its recurring value is clear. '
            'Explain the outcome before asking customers to commit to a subscription.')
    result = module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
        min_duration=35, max_duration=35, require_standalone=True)
    assert result[0]['quality']['promotional'] is False


@pytest.mark.parametrize('text', [
    "He hasn't spoken since he left Manchester United. He's back working in the Netherlands now.",
    "That's all positive from Tenhog on the current boss Michael Carrick. Michael Carrick has a news conference today.",
    "We've got another voice note. This one's from Jacob. I've got loads of respect for Tennog.",
    "I suppose he wasn't there either, was he? He wasn't there at that time because he was at Middlesbrough.",
])
def test_strict_planning_rejects_context_and_host_setups_seen_in_past_exports(text):
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
            min_duration=35, max_duration=35, require_standalone=True)


@pytest.mark.parametrize('text', [
    'It is a mistake to hire before planning payroll. Keep reserves to cover salary payments.',
    "It's a mistake to hire before planning payroll. Keep reserves to cover salary payments.",
    'This is why cash reserves matter. They protect payroll before invoices are paid.',
    'Why is it hard to hire good people? Define the role before interviewing.',
    'Why does that team need a cash reserve? Late invoices can leave payroll unfunded.',
    'He, Erik ten Hag, explained why Manchester United needed patience. Give a manager clear goals.',
])
def test_strict_planning_keeps_complete_hooks_with_an_explicit_subject(text):
    choice = module().suggest_cuts([{'start': 0, 'end': 35, 'text': text}], 35,
        min_duration=35, max_duration=35, require_standalone=True)[0]
    assert choice['quality']['context_dependent_opening'] is False


def _previous_payoff_check(text):
    # Retain the full-window predicate as a differential oracle for optimization.
    return bool(re.search(
        r"(?:let me tell you what|here['’]s (?:the thing|what)|my (?:line of )?question(?:ing)?[^.!?]*|"
        r"(?:it['’]s|it is) (?:really )?(?:just )?to (?:understand|know)[^.!?]*|"
        r"(?:i|we) (?:want|would like|am trying|are trying) to (?:understand|know)[^.!?]*)"
        r'''[.!?]["'”’»」』）)\]}]*$''', text, re.IGNORECASE))


def test_payoff_check_limits_regex_work_to_the_final_sentence(monkeypatch):
    mod = module()
    search = mod.re.search
    scanned = []

    def recording_search(pattern, text, *args, **kwargs):
        scanned.append(len(text))
        return search(pattern, text, *args, **kwargs)

    monkeypatch.setattr(mod.re, 'search', recording_search)
    final_sentence = ' Here’s the thing.”'
    earlier = ('A complete point about payroll. ' * 100).rstrip()
    assert mod._needs_payoff(earlier + final_sentence)
    assert scanned and max(scanned) <= len(final_sentence)


def test_payoff_check_matches_previous_policy_for_generated_caption_windows():
    mod = module()
    prefixes = ['', 'A complete point. ', 'A question? ', 'A warning! ', 'An unfinished thought ',
                'The example.com project worked. ', 'My question is answered. ']
    endings = ['', '.', '!', '?', '."', '?”', '!’»」』）)]}', '.\n', '. ', '...']
    statements = [
        'Let me tell you what', 'Here’s the thing', "Here's what", 'My question is why payroll failed',
        'My line of questioning is to understand the result', 'It is really just to know the result',
        'I want to understand the result', 'We would like to know the result',
        'I am trying to understand the result', 'We are trying to know the result',
        'Cash reserves protect payroll', 'Here is the thing', 'WHY DOES PAYROLL MATTER',
        '稳定的现金流支持团队。',
    ]
    corpus = [prefix + statement + ending
              for prefix in prefixes for statement in statements for ending in endings]
    rng = random.Random(2761)
    fragments = [*prefixes, *statements, *endings, '\n', '\u2028', '\u00a0', '\u0301', '\u2026']
    corpus.extend(''.join(rng.choices(fragments, k=rng.randrange(1, 12))) for _ in range(2000))
    for text in corpus:
        assert mod._needs_payoff(text) == _previous_payoff_check(text), repr(text)


def test_payoff_optimization_preserves_complete_ranked_suggestions(monkeypatch):
    from app.core.config import load_settings
    mod = module()
    statements = [
        'Budgeting protects payroll. Build three cash reserves before hiring.',
        'What makes a team successful? Clear roles help people make better decisions.',
        'A written checklist protects suppliers. Review each payment before sending it.',
        'My line of questioning is just to understand',
        'how people make decisions. Clear roles reduce confusion.',
        'Let me tell you what.',
        'Planning protects the business. Here’s the thing.',
        'Practice improves judgment. Review each decision after finishing the project.',
        'Written goals help teams focus. Review one priority at the start of each day.',
        'Customers explain useful problems. Ask for an example before building a feature.',
        'Financial planning gives teams time. Keep a cash reserve for unexpected costs.',
        'Useful feedback improves the next decision. Review the result after the project.',
        'Clear roles improve hiring. Describe the responsibility before interviewing.',
        'A checklist protects attention. Write down each required action before starting.',
        'Small experiments expose weak ideas. Test the central assumption first.',
        'Customer interviews reveal priorities. Listen for the task people repeat.',
    ]
    transcript = [{'start': index * 4, 'end': (index + 1) * 4,
                   'text': statements[index % len(statements)]} for index in range(48)]
    settings = load_settings(environ={})
    arguments = dict(target_duration=30, min_duration=15, max_duration=40, keywords='business,payroll',
                     limit=5, min_gap=3, require_standalone=True, settings=settings,
                     rank_by_growth=True)
    optimized = mod.suggest_cuts(transcript, 192, **arguments)
    assert optimized
    monkeypatch.setattr(mod, '_needs_payoff', _previous_payoff_check)
    assert mod.suggest_cuts(transcript, 192, **arguments) == optimized


@pytest.mark.parametrize('title', ['Intro', ' Introduction ', 'OUTRO', 'Sponsor', 'Sponsorship',
                                  'Advertising', 'Advertisement', 'Ad', 'Ad break', 'Commercial break'])
def test_strict_planning_rejects_explicit_intro_outro_and_advertising_chapters(title):
    transcript = [{'start': 100, 'end': 135,
                   'text': 'A written plan protects payroll. Assign one owner to each payment.'}]
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts(transcript, 200, min_duration=35, max_duration=35,
            require_standalone=True, chapters=[{'start_time': 100, 'end_time': 135, 'title': title}])


@pytest.mark.parametrize('title', ['Introduction to Algebra', 'Advertising advice',
                                  'How to find a sponsor', 'Career advice', 'Intro to programming'])
def test_strict_planning_keeps_educational_chapter_topics(title):
    transcript = [{'start': 100, 'end': 135,
                   'text': 'A written plan protects payroll. Assign one owner to each payment.'}]
    result = module().suggest_cuts(transcript, 200, min_duration=35, max_duration=35,
        require_standalone=True, chapters=[{'start_time': 100, 'end_time': 135, 'title': title}])
    assert result[0]['clip_plan']['start_seconds'] == 100


def test_strict_planning_filters_crossing_chapters_before_choosing_the_best_end():
    transcript = [{'start': 0, 'end': 20, 'text': 'A written plan protects payroll.'},
                  {'start': 20, 'end': 40, 'text': 'Assign one owner to each payment.'}]
    result = module().suggest_cuts(transcript, 40, target_duration=40, min_duration=20, max_duration=40,
        require_standalone=True, chapters=[{'start_time': 30, 'end_time': 35, 'title': 'Sponsor'}])
    assert [item['clip_plan'] for item in result] == [
        {'start_seconds': 0, 'duration_seconds': 20, 'aspect_ratio': '9:16'}]


@pytest.mark.parametrize('chapters', [None, [], {}, [None],
    [{'title': 'Intro', 'start_time': True, 'end_time': 35}],
    [{'title': 'Intro', 'start_time': -1, 'end_time': 35}],
    [{'title': 'Intro', 'start_time': 30, 'end_time': 20}],
    [{'title': 'Intro', 'start_time': 0, 'end_time': float('inf')}],
    [{'title': 'Intro', 'start_time': 0, 'end_time': 300}],
    [{'title': 'Intro', 'start_time': 0}],
    [{'start_time': 0, 'end_time': 35}],
])
def test_missing_or_malformed_chapters_do_not_fabricate_exclusions(chapters):
    transcript = [{'start': 0, 'end': 35,
                   'text': 'A written plan protects payroll. Assign one owner to each payment.'}]
    assert module().suggest_cuts(transcript, 35, min_duration=35, max_duration=35,
        require_standalone=True, chapters=chapters)


def test_strict_chapter_exclusion_uses_source_times_and_allows_touching_boundaries():
    transcript = [{'start': 325, 'end': 360,
                   'text': 'A written plan protects payroll. Assign one owner to each payment.'}]
    source = {'chapters': [{'start_time': 0, 'end_time': 325, 'title': 'Intro'},
                           {'start_time': 360, 'end_time': 400, 'title': 'Outro'}]}
    result = module().suggest_cuts(transcript, 400, min_duration=35, max_duration=35,
                                   require_standalone=True, source=source)
    assert result[0]['clip_plan']['start_seconds'] == 325


def test_empty_explicit_chapters_do_not_hide_known_source_introduction():
    transcript = [{'start': 0, 'end': 35,
                   'text': 'A written plan protects payroll. Assign one owner to each payment.'}]
    with pytest.raises(ValueError, match='window'):
        module().suggest_cuts(transcript, 35, min_duration=35, max_duration=35,
            require_standalone=True, chapters=[],
            source={'chapters': [{'start_time': 0, 'end_time': 35, 'title': 'Intro'}]})
