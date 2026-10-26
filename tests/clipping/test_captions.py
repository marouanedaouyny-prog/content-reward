import json
from pathlib import Path

import pytest

from clipping import media


@pytest.fixture
def render_subtitles(tmp_path, monkeypatch):
    folder = tmp_path / 'render'
    folder.mkdir()
    selected = {}

    def encode(args, **kwargs):
        Path(args[-1]).write_bytes(b'fixture' * 300)

    def probe(path):
        return {'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 1080, 'height': 1920},
                            {'codec_type': 'audio', 'codec_name': 'aac'}],
                'format': {'duration': selected['duration']}}

    monkeypatch.setattr(media, 'command', encode)
    monkeypatch.setattr(media, 'probe', probe)
    # These tests isolate subtitle grouping; mechanical media QC is tested separately.
    from clipping.quality.validation import QualityResult
    monkeypatch.setattr('clipping.quality.validation.validate_media', lambda *args, **kwargs:
                        QualityResult(passed=True, score=100, checks={'fixture_only': True}))

    def render(segments, start, duration, source_duration=10):
        selected['duration'] = duration
        (folder / 'transcript.json').write_text(json.dumps({'segments': segments}), encoding='utf-8')
        result = media.render({'clip_plan': {'start_seconds': start, 'duration_seconds': duration,
                                           'aspect_ratio': '9:16'}},
                              {'source_path': 'source.mp4', 'source_duration': source_duration,
                               'transcript_path': 'render/transcript.json'}, folder, tmp_path)
        text = (tmp_path / result['subtitle_path']).read_text(encoding='utf-8')
        return media.parse_srt(text), text

    return render


def word_segment(tokens, interval=.5):
    words = [{'start': i * interval, 'end': (i + 1) * interval - .1,
              'word': (' ' if i else '') + token} for i, token in enumerate(tokens)]
    return {'start': 0, 'end': len(tokens) * interval,
            'text': ' '.join(tokens), 'words': words}


def test_long_speech_is_rendered_as_short_timed_phrases(render_subtitles):
    tokens = 'Readable captions keep the words close to the audio and show short phrases instead of one paragraph'.split()
    segment = word_segment(tokens)
    cues, text = render_subtitles([segment], 0, 10)
    assert len(cues) > 1
    assert ' '.join(cue['text'] for cue in cues) == segment['text']
    assert all(len(cue['text'].split()) <= 6 for cue in cues)
    assert all(len(block.splitlines()[2:]) <= 2 for block in text.strip().split('\n\n'))
    assert cues[0]['start'] == segment['words'][0]['start']
    assert cues[-1]['end'] == segment['words'][-1]['end']


def test_clip_window_excludes_words_before_and_after_the_cut(render_subtitles):
    segment = word_segment('one two three four five six seven eight nine ten'.split())
    cues, _ = render_subtitles([segment], 2, 2)
    assert ' '.join(cue['text'] for cue in cues) == 'five six seven eight'
    assert cues[0]['start'] == 0
    assert cues[-1]['end'] == 1.9


def test_words_crossing_cut_boundaries_use_only_the_available_interval(render_subtitles):
    segment = word_segment('one two three four'.split())
    cues, _ = render_subtitles([segment], .2, .5)
    assert cues == [{'start': 0, 'end': .5, 'text': 'one two'}]


def test_aligned_words_outside_parent_segment_are_not_lost(render_subtitles):
    segment = {'start': .4, 'end': 2, 'text': 'Hello.', 'words': [
        {'start': .2, 'end': 2.1, 'word': ' Hello.'}]}
    cues, _ = render_subtitles([segment], 0, 3)
    assert cues == [{'start': .2, 'end': 2.1, 'text': 'Hello.'}]


def test_captions_do_not_stay_visible_through_a_long_speech_pause(render_subtitles):
    segment = {'start': 0, 'end': 4, 'text': 'Read this. Check timing.', 'words': [
        {'start': 0, 'end': .3, 'word': 'Read'}, {'start': .3, 'end': .8, 'word': ' this.'},
        {'start': 3, 'end': 3.4, 'word': ' Check'}, {'start': 3.4, 'end': 3.8, 'word': ' timing.'}]}
    cues, _ = render_subtitles([segment], 0, 4)
    assert len(cues) == 2
    assert cues[0]['end'] == .8 and cues[1]['start'] == 3


def test_cjk_word_text_is_joined_without_inventing_spaces(render_subtitles):
    segment = {'start': 0, 'end': 2, 'text': '\u6d4b\u8bd5\u3002', 'words': [
        {'start': 0, 'end': .5, 'word': '\u6d4b'},
        {'start': .5, 'end': .9, 'word': '\u8bd5'},
        {'start': .9, 'end': 1.2, 'word': '\u3002'}]}
    cues, _ = render_subtitles([segment], 0, 2)
    assert cues == [{'start': 0, 'end': 1.2, 'text': '\u6d4b\u8bd5\u3002'}]


def test_slow_speech_does_not_make_a_phrase_exceed_three_seconds(render_subtitles):
    segment = word_segment('one two three four'.split(), interval=1)
    cues, _ = render_subtitles([segment], 0, 4)
    assert len(cues) == 2
    assert all(cue['end'] - cue['start'] <= 3 for cue in cues)


def test_segment_only_subtitles_keep_their_original_timing(render_subtitles):
    segment = {'start': .4, 'end': 3.6, 'text': 'A supplied timed subtitle stays intact.'}
    cues, _ = render_subtitles([segment], 0, 4)
    assert cues == [segment]


def test_zero_duration_words_use_neighboring_alignment_without_dropping_text(render_subtitles):
    segment = {'start': 0, 'end': 3, 'text': 'What then.', 'words': [
        {'start': 0, 'end': .5, 'word': 'What'}, {'start': .5, 'end': .5, 'word': ' then.'}]}
    cues, _ = render_subtitles([segment], 0, 3)
    assert cues == [{'start': 0, 'end': .5, 'text': 'What then.'}]


def test_zero_duration_words_do_not_turn_a_long_sentence_into_a_caption_paragraph(render_subtitles):
    tokens = 'I mean, I went through a phase where I ripped through like ten secretaries in two years.'.split()
    segment = word_segment(tokens, interval=.2)
    segment['words'][0]['end'] = segment['words'][0]['start']
    segment['words'][2]['end'] = segment['words'][2]['start']
    cues, text = render_subtitles([segment], 0, 4)
    assert ' '.join(cue['text'] for cue in cues) == segment['text']
    assert all(len(cue['text'].split()) <= 6 for cue in cues)
    assert all(len(block.splitlines()[2:]) <= 2 for block in text.strip().split('\n\n'))
    assert all(0 <= cue['start'] < cue['end'] <= 4 for cue in cues)


def test_zero_duration_words_before_the_cut_are_not_added_to_the_next_caption(render_subtitles):
    segment = {'start': .5, 'end': 2, 'text': 'Before after.', 'words': [
        {'start': .5, 'end': .5, 'word': 'Before'},
        {'start': 1, 'end': 2, 'word': ' after.'}]}
    cues, _ = render_subtitles([segment], 1, 1)
    assert cues == [{'start': 0, 'end': 1, 'text': 'after.'}]


def test_invalid_saved_word_metadata_is_not_rendered(render_subtitles):
    segment = {'start': 0, 'end': 2, 'text': 'Original.', 'words': [
        {'start': 0, 'end': 2, 'word': ' Altered.'}]}
    with pytest.raises(ValueError, match='Word text'):
        render_subtitles([segment], 0, 2)


def test_disfluency_only_word_segment_does_not_produce_an_empty_caption():
    from clipping.captions import cues_for_window
    segment = {'start': 0, 'end': 1, 'text': 'Um uh.', 'words': [
        {'start': 0, 'end': .5, 'word': ' Um'}, {'start': .5, 'end': 1, 'word': ' uh.'}]}
    assert cues_for_window([segment], 0, 1) == []
