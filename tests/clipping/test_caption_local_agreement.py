"""Substantial timed disagreements cannot hide in a matching whole clip."""

from clipping.caption_review import assess_captions


def timed_segment(start, end, text):
    tokens = text.split()
    interval = (end - start) / len(tokens)
    return {'start': start, 'end': end, 'text': text, 'words': [
        {'start': start + index * interval,
         'end': start + (index + 1) * interval - .001, 'word': token}
        for index, token in enumerate(tokens)]}


def test_bad_ten_second_passage_is_not_hidden_by_good_neighboring_captions():
    # Inspired by an actual tiny.en export. Good surrounding captions lifted
    # whole-clip recall above .79 while this central cue retained only .64.
    reference = [
        {'start': 0, 'end': 10,
         'text': 'I am not a gambler in the actual clinical sense but I take risks '
                 'when a new opportunity gives us something useful to build.'},
        {'start': 10, 'end': 20,
         'text': 'AI is here to stay and I wanted to put human creativity and AI '
                 'together and of course everyone is going nuts about that.'},
        {'start': 20, 'end': 30,
         'text': 'happening guys you know people are now selling their images this '
                 'and eventually there are uh the 20 of uses avatars there that is happening'},
        {'start': 30, 'end': 40,
         'text': 'So I would take that risk even though you get blasted bombastically '
                 'from the creative community and they are right about their concerns.'},
        {'start': 40, 'end': 50,
         'text': 'But we cannot stop this avalanche because it is out of our control '
                 'and we need a way to adapt as these tools keep changing.'},
    ]
    # Keep speech outside neighboring cues' timing tolerance so they cannot
    # accidentally supply the missing words in this intentionally isolated test.
    segments = [timed_segment(cue['start'] + .8, cue['end'] - .8, cue['text'])
                for cue in reference]
    segments[2] = timed_segment(20.8, 29.2,
        'happening guys you know people are now selling the room engine this '
        'intervention is there are 20 helplesses avatars is happening')
    result = assess_captions(segments, 0, 50, reference)
    assert result['source_token_recall'] > .79
    assert result['source_token_precision'] > .8
    assert result['ordered_token_recall'] > .79
    assert result['expected_speech_coverage'] > .8
    assert result['passed'] is False
    assert result['failures'] == ['timed_source_disagreement']
    check = result['local_source_checks']['checks'][2]
    assert check['source_token_recall'] == .64
    assert check['passed'] is False


def test_local_comparison_tolerates_minor_recognition_differences():
    reference = [{'start': 0, 'end': 10,
                  'text': 'Good planning lets every player improve their skills with practice.'}]
    segments = [timed_segment(0, 10,
                'Good planning helps every player improve their skills with training.')]
    result = assess_captions(segments, 0, 10, reference)
    assert result['passed'] is True, result
    assert result['local_source_checks']['checks'][0]['source_token_recall'] == .8


def test_locally_scrambled_words_are_not_hidden_by_matching_neighboring_captions():
    reference = [
        {'start': 0, 'end': 10,
         'text': 'The initial design looked simple and worked well when the team tested it.'},
        {'start': 10, 'end': 20,
         'text': 'Clear plans help every player build useful skills through practice'},
        {'start': 20, 'end': 30,
         'text': 'After the inspection we replaced each damaged component before proceeding with delivery.'},
    ]
    segments = [timed_segment(cue['start'] + .8, cue['end'] - .8, cue['text'])
                for cue in reference]
    segments[1] = timed_segment(10.8, 19.2,
                               'build player every help plans Clear useful skills through practice')
    result = assess_captions(segments, 0, 30, reference)
    assert result['source_token_recall'] == 1
    assert result['ordered_token_recall'] > .8
    assert result['passed'] is False
    assert result['failures'] == ['timed_source_disagreement']
    assert result['local_source_checks']['checks'][1]['ordered_token_recall'] == .5


def test_local_comparison_preserves_public_cue_timing_tolerance():
    reference = [{'start': 2, 'end': 4,
                  'text': 'Good planning helps every player improve their skills.'}]
    segments = [timed_segment(2.7, 4.7, reference[0]['text'])]
    result = assess_captions(segments, 0, 6, reference)
    assert result['local_source_checks']['failed'] == 0, result
    assert result['local_source_checks']['timing_tolerance_seconds'] == .75


def test_short_name_only_cues_are_not_used_to_prove_local_disagreement():
    reference = [
        {'start': 0, 'end': 2, 'text': 'Craig Borsari'},
        {'start': 2, 'end': 10,
         'text': 'The clear plan gives everyone enough time to finish their work.'},
    ]
    segments = [timed_segment(0, 2, 'Greg Barsari'), timed_segment(2, 10, reference[1]['text'])]
    result = assess_captions(segments, 0, 10, reference)
    assert result['passed'] is True, result
    assert result['local_source_checks']['evaluated'] == 1
    assert result['speech_accuracy'] == 'not_verified'
