import re

import pytest


def transcript():
    tokens = ['Build', 'a', 'successful', 'business.']
    return [{'start': 0, 'end': 2, 'text': ' '.join(tokens), 'words': [
        {'start': i * .5, 'end': i * .5 + .4, 'word': (' ' if i else '') + token}
        for i, token in enumerate(tokens)]}]


def events(document):
    return [line.split(',', 9) for line in document.splitlines() if line.startswith('Dialogue:')]


def visible(text):
    return ' '.join(re.sub(r'\{[^}]*\}', '', text).replace(r'\N', ' ').split())


def test_colorized_style_tracks_the_actual_spoken_word_without_moving_the_caption():
    from clipping.caption_styles import ass_for_window
    document = ass_for_window(transcript(), 0, 2, 1080, 1920, 'colorized')
    rows = events(document)
    assert rows
    assert all(visible(row[9]) in ('BUILD A SUCCESSFUL', 'BUSINESS.') for row in rows)
    assert {visible(row[9]) for row in rows} == {'BUILD A SUCCESSFUL', 'BUSINESS.'}
    build = next(row for row in rows if row[1] == '0:00:00.00')
    business = next(row for row in rows if row[1] == '0:00:01.50')
    assert r'{\1c&H6BFF7C&}BUILD{\1c&HFFFFFF&}' in build[9]
    assert r'{\1c&H6BFF7C&}BUSINESS.{\1c&HFFFFFF&}' in business[9]
    assert all(r'\pos' not in row[9] and r'\fs' not in row[9] for row in rows)


def test_professional_style_keeps_case_and_emphasizes_keywords_in_gold():
    from clipping.caption_styles import ass_for_window
    rows = events(ass_for_window(transcript(), 0, 2, 1080, 1920, 'pro'))
    assert len(rows) == 2
    assert ' '.join(visible(row[9]) for row in rows) == 'Build a successful business.'
    assert r'{\1c&H5FC8F6&}business{\1c&HF3F3EE&}' in rows[1][9]
    assert rows[0][1:3] == ['0:00:00.00', '0:00:01.40']
    assert rows[1][1:3] == ['0:00:01.50', '0:00:01.90']


def test_colorized_style_does_not_guess_word_timing_from_a_segment_only_transcript():
    from clipping.caption_styles import ass_for_window
    rows = events(ass_for_window([{'start': 0, 'end': 1, 'text': 'Stay real.'}],
                                 0, 1, 1080, 1920, 'colorized'))
    assert len(rows) == 1
    assert visible(rows[0][9]) == 'STAY REAL.'
    assert r'\1c' not in rows[0][9]


def test_caption_styles_keep_the_cut_boundaries_and_cannot_inject_ass_commands():
    from clipping.caption_styles import ass_for_window
    words = transcript()
    rows = events(ass_for_window(words, 1, .7, 1080, 1920, 'colorized'))
    assert all(visible(row[9]) == 'SUCCESSFUL BUSINESS.' for row in rows)
    assert rows[0][1] == '0:00:00.00' and rows[-1][2] == '0:00:00.70'
    unsafe = [{'start': 0, 'end': 1, 'text': r'{\pos(0,0)}hello\Nworld'}]
    row = events(ass_for_window(unsafe, 0, 1, 1080, 1920, 'pro'))[0]
    assert r'\pos(0,0)' not in row[9]
    assert 'hello' in row[9] and 'world' in row[9]


@pytest.mark.parametrize('style', ['unknown', '../file', None, 1])
def test_unknown_styles_are_rejected(style):
    from clipping.caption_styles import ass_for_window
    with pytest.raises(ValueError, match='caption style'):
        ass_for_window(transcript(), 0, 2, 1080, 1920, style)
