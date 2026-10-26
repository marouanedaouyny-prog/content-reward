"""Caption coverage is checked against actual selected source speech."""

import importlib

import pytest


def assess(segments, start, duration, reference):
    return importlib.import_module('clipping.caption_review').assess_captions(
        segments, start, duration, reference)


def first_reference():
    # Actual cached interview, source5051.59–5071.59; section starts5048.59.
    return [
        {'start': 3, 'end': 7.52,
         'text': 'Yes, sir. I agree. We should do a fight at the White House. And then now Craig Borsari came to me'},
        {'start': 7.52, 'end': 16.38,
         'text': "with his own idea that I think is fucking brilliant. And I'm working on that one now. But we don't"},
        {'start': 16.38, 'end': 23,
         'text': "can't be done. Not only will we do it and do it at the level that just blows people's minds."},
    ]


def test_real_prompted_tail_only_asr_does_not_pass_a_complete_source_window():
    # Actual failure: a full-speech initial_prompt suppressed the selected audio.
    segments = [{'start': 22.68, 'end': 25.98, 'text': 'Why will you win at boxing? First of all...',
        'words': [{'start': 22.68, 'end': 23.2, 'word': ' Why'},
                  {'start': 23.2, 'end': 23.72, 'word': ' will'},
                  {'start': 23.72, 'end': 23.96, 'word': ' you'},
                  {'start': 23.96, 'end': 24.28, 'word': ' win'},
                  {'start': 24.28, 'end': 24.48, 'word': ' at'},
                  {'start': 24.48, 'end': 24.74, 'word': ' boxing?'}]}]
    result = assess(segments, 3, 20, first_reference())
    assert result['passed'] is False
    assert result['source_token_recall'] < .1
    assert result['caption_fraction'] < .05
    assert 'insufficient_reference_text' in result['failures']
    assert 'insufficient_speech_coverage' in result['failures']


def test_three_words_with_inflated_timing_cannot_cover_twenty_seconds_of_speech():
    result = assess([{'start': 3, 'end': 23, 'text': 'We should fight.'}], 3, 20, first_reference())
    assert result['passed'] is False
    assert 'insufficient_reference_text' in result['failures']


def test_coarse_unprompted_segments_require_review_when_local_timing_is_unestablished():
    # The first ASR segment spans the public cue boundary at 7.52 seconds.
    # Without word timings its midpoint cannot establish the latter half of
    # that segment as evidence for the following independent source cue.
    segments = [
        {'start': 3, 'end': 9.84, 'text': "Yes sir, I agree. We should do a fight at the White House. And then now Craig Borsari came to me with his own idea that I think is fucking brilliant."},
        {'start': 9.84, 'end': 15.28, 'text': "And I'm working on that one now. But we don't say no at the UFC. It's just we always, whatever people"},
        {'start': 15.28, 'end': 20.82, 'text': "think is impossible and can't be done. Not only will we do it, you do it at the level that"},
        {'start': 21.7, 'end': 22.96, 'text': "just blows people's minds."},
    ]
    result = assess(segments, 3, 20, first_reference())
    assert result['passed'] is False, result
    assert result['failures'] == ['timed_source_disagreement']
    assert result['local_source_checks']['checks'][1]['source_token_recall'] == .5
    assert result['source_token_recall'] > .8
    assert .8 < result['speech_caption_intersection_fraction'] <= 1


def test_natural_silence_between_short_answers_does_not_require_continuous_captions():
    reference = [{'start': 3, 'end': 4, 'text': 'Yes, absolutely.'},
                 {'start': 17, 'end': 18, 'text': 'No, never.'}]
    segments = [{'start': 3.1, 'end': 3.9, 'text': 'Yes, absolutely.'},
                {'start': 17.1, 'end': 17.9, 'text': 'No, never.'}]
    result = assess(segments, 0, 20, reference)
    assert result['passed'] is True, result
    assert result['caption_fraction'] == pytest.approx(.08)
    assert result['expected_speech_fraction'] == pytest.approx(.1)
    assert result['expected_speech_coverage'] == pytest.approx(.8)


def test_hallucinated_power_slap_repetition_is_rejected():
    reference = [{'start': 0, 'end': 20, 'text':
        "My goal is to get into boxing. I got power slap. Next I want to build another great fight brand and take on a bigger challenge."}]
    result = assess([{'start': 0, 'end': 20, 'text': 'I got power slap. ' * 12}], 0, 20, reference)
    assert result['passed'] is False
    assert result['excess_repetition'] is True
    assert 'excessive_repetition' in result['failures']


def test_refrain_present_in_reference_is_not_marked_as_hallucinated_repetition():
    text = 'Practice makes progress. ' * 4
    reference = [{'start': 0, 'end': 15, 'text': text}]
    result = assess(reference, 0, 15, reference)
    assert result['passed'] is True
    assert result['excess_repetition'] is False


def test_words_outside_selected_window_do_not_inflate_caption_coverage_or_recall():
    result = assess([{'start': 0, 'end': 30, 'text': 'A clear plan prevents mistakes.', 'words': [
        {'start': 0, 'end': 1, 'word': 'A clear plan prevents mistakes.'},
        {'start': 25, 'end': 26, 'word': 'A clear plan prevents mistakes.'}]}],
        5, 15, [{'start': 5, 'end': 20, 'text': 'A clear plan prevents mistakes.'}])
    assert result['passed'] is False
    assert result['caption_word_count'] == 0
    assert result['caption_fraction'] == 0


def test_zero_duration_hallucinated_words_are_not_timed_caption_evidence():
    segments = [{'start': 0, 'end': 20, 'text': 'A clear plan prevents mistakes.', 'words': [
        {'start': 19, 'end': 19, 'word': 'A clear plan prevents mistakes.'}]}]
    result = assess(segments, 0, 20, [{'start': 0, 'end': 20, 'text': segments[0]['text']}])
    assert result['passed'] is False
    assert result['caption_word_count'] == 0
    assert result['caption_fraction'] == 0


def test_empty_reference_is_an_explicit_review_failure():
    result = assess([{'start': 0, 'end': 20, 'text': 'A complete sentence.'}], 0, 20, [])
    assert result['passed'] is False
    assert 'missing_reference' in result['failures']


def test_half_the_source_words_cannot_pass_with_inflated_full_window_timing():
    reference = [{'start': 0, 'end': 10,
                  'text': 'A clear plan helps every player improve their skills with practice.'}]
    result = assess([{'start': 0, 'end': 10, 'text': 'A clear plan helps every player.'}],
                    0, 10, reference)
    assert result['passed'] is False
    assert 'insufficient_reference_text' in result['failures']


def test_hallucinated_insertions_are_rejected_even_when_every_source_word_is_present():
    source = 'A clear plan helps every player improve their skills with practice.'
    extra = ' astronaut cereal purple zigzag invention mountain bookshelf tiger moon rocket banana candle unicycle'
    result = assess([{'start': 0, 'end': 10, 'text': source + extra}], 0, 10,
                    [{'start': 0, 'end': 10, 'text': source}])
    assert result['passed'] is False
    assert 'unsupported_caption_text' in result['failures']
    assert result['source_token_precision'] < .5


def test_same_words_in_reverse_order_do_not_establish_source_speech_agreement():
    source = 'A clear plan helps every player improve their skills with practice.'
    result = assess([{'start': 0, 'end': 10, 'text': ' '.join(reversed(source.split()))}],
                    0, 10, [{'start': 0, 'end': 10, 'text': source}])
    assert result['passed'] is False
    assert 'source_word_order' in result['failures']


def test_matching_words_in_the_wrong_timed_source_cue_do_not_pass():
    reference = [
        {'start': 0, 'end': 5, 'text': 'Never buy a fake product from an unverified shop.'},
        {'start': 5, 'end': 10, 'text': 'Choose the genuine replacement after checking its official serial number.'},
    ]
    result = assess([dict(reference[0], text=reference[1]['text']),
                     dict(reference[1], text=reference[0]['text'])], 0, 10, reference)
    assert result['passed'] is False
    assert 'timed_source_disagreement' in result['failures']
    assert result['local_source_checks']['failed'] == 2


def test_omission_concentrated_in_one_cue_is_not_hidden_by_other_matching_cues():
    reference = [
        {'start': 0, 'end': 5, 'text': 'The initial design looked simple and worked well in practice.'},
        {'start': 5, 'end': 8, 'text': 'However never connect both exposed wires to the power supply.'},
        {'start': 8, 'end': 13, 'text': 'After the inspection we replaced each damaged component before proceeding.'},
        {'start': 13, 'end': 18, 'text': 'The resulting machine passed every safety check before delivery.'},
    ]
    result = assess([reference[0], reference[2], reference[3]], 0, 18, reference)
    assert result['passed'] is False
    assert 'timed_source_disagreement' in result['failures']


def test_small_word_timing_jitter_at_a_cut_is_tolerated():
    segment = {'start': 2.98, 'end': 6.02, 'text': 'A complete thought.', 'words': [
        {'start': 2.98, 'end': 3.2, 'word': ' A'},
        {'start': 3.2, 'end': 5, 'word': ' complete'},
        {'start': 5, 'end': 6.02, 'word': ' thought.'}]}
    result = assess([segment], 3, 3, [{'start': 3, 'end': 6, 'text': segment['text']}])
    assert result['passed'] is True, result


@pytest.mark.parametrize('edge', ['leading', 'trailing'])
def test_context_word_fragments_at_the_cut_need_review(edge):
    words = [{'start': 3.2, 'end': 3.4, 'word': ' A'},
             {'start': 3.4, 'end': 4.5, 'word': ' complete'},
             {'start': 4.5, 'end': 5.6, 'word': ' thought.'}]
    words.insert(0, {'start': 2.7, 'end': 3.04, 'word': ' me.'}) if edge == 'leading' else words.append(
        {'start': 5.88, 'end': 6.32, 'word': ' What'})
    segment = {'start': 2.7, 'end': 6.32, 'text': ''.join(w['word'] for w in words), 'words': words}
    result = assess([segment], 3, 3, [{'start': 3, 'end': 6, 'text': 'A complete thought.'}])
    assert result['passed'] is False
    assert 'clipped_boundary_word' in result['failures']
    assert result['boundary_words'][0]['edge'] == edge


def test_caption_agreement_explicitly_preserves_unverified_speech_accuracy():
    cues = [{'start': 0, 'end': 5, 'text': 'A complete point.'}]
    result = assess(cues, 0, 5, cues)
    assert result['passed'] is True
    assert result['speech_accuracy'] == 'not_verified'
    assert result['source_token_precision'] == 1
    assert result['ordered_token_recall'] == 1
    assert result['local_source_checks']['evaluated'] == 0
    assert result['limitations']
