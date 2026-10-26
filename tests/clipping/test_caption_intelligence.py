"""Caption intelligence: configured grouping, display cleanup and emphasis."""

import re

from clipping.captions import cues_for_window, display_text
from clipping.caption_styles import ass_for_window


def overlay(tmp_path, monkeypatch, text):
    from app.core.config import load_settings, read_yaml
    path = tmp_path / 'overlay.yaml'
    path.write_text(text, encoding='utf-8')
    monkeypatch.setenv('CONTENT_REWARD_CONFIG', str(path))
    read_yaml.cache_clear()
    return load_settings()


def word_segment(tokens, interval=.5):
    words = [{'start': i * interval, 'end': (i + 1) * interval - .1,
              'word': (' ' if i else '') + token} for i, token in enumerate(tokens)]
    return {'start': 0, 'end': len(tokens) * interval, 'text': ' '.join(tokens), 'words': words}


def events(document):
    return [line.split(',', 9) for line in document.splitlines() if line.startswith('Dialogue:')]


def visible(text):
    return ' '.join(re.sub(r'\{[^}]*\}', '', text).replace(r'\N', ' ').split())


def test_display_cleanup_removes_only_zero_meaning_disfluencies():
    assert display_text('Um, he left. Uh... nobody knew.') == 'he left. nobody knew.'
    # Meaning-carrying hesitation words are deliberately kept.
    assert display_text('I like, you know, basically built it.') == 'I like, you know, basically built it.'
    assert display_text('Umbrella and human stay.') == 'Umbrella and human stay.'


def test_captions_drop_uh_and_um_from_timed_phrases():
    segment = word_segment('Um he made a bold decision uh nobody knew'.split())
    cues = cues_for_window([segment], 0, 4.5)
    text = ' '.join(cue['text'] for cue in cues).replace('\n', ' ')
    assert text == 'he made a bold decision nobody knew'
    # Timing of kept words is preserved.
    assert cues[0]['start'] == .5


def test_filler_cleanup_can_be_disabled(tmp_path, monkeypatch):
    settings = overlay(tmp_path, monkeypatch, 'captions: {remove_fillers: false}\n')
    segment = word_segment('Um he made a bold decision'.split())
    cues = cues_for_window([segment], 0, 2, settings=settings)
    assert ' '.join(cue['text'] for cue in cues).startswith('Um he made')


def test_words_per_line_config_groups_shorter_phrases(tmp_path, monkeypatch):
    settings = overlay(tmp_path, monkeypatch, 'captions: {words_per_line: 4}\n')
    segment = word_segment('one two three four five six seven eight'.split())
    cues = cues_for_window([segment], 0, 4, settings=settings)
    assert all(len(cue['text'].replace('\n', ' ').split()) <= 4 for cue in cues)


def test_default_grouping_is_preserved_without_overrides(tmp_path, monkeypatch):
    settings = overlay(tmp_path, monkeypatch, 'captions: {words_per_line: 6}\n')
    segment = word_segment('one two three four five six seven eight'.split())
    cues = cues_for_window([segment], 0, 4, settings=settings)
    assert all(len(cue['text'].replace('\n', ' ').split()) <= 6 for cue in cues)


def test_pro_style_emphasizes_money_numbers_and_results():
    segment = word_segment('He made $50,000 in 7 days after the scam collapsed'.split())
    rows = events(ass_for_window([segment], 0, 5, 1080, 1920, 'pro'))
    text = ' '.join(row[9] for row in rows)
    assert r'{\1c&H5FC8F6&}$50,000{\1c&HF3F3EE&}' in text
    assert r'{\1c&H5FC8F6&}7{\1c&HF3F3EE&}' in text
    assert r'{\1c&H5FC8F6&}scam{\1c&HF3F3EE&}' in text


def test_highlight_active_word_config_disables_colorized_karaoke(tmp_path, monkeypatch):
    settings = overlay(tmp_path, monkeypatch, 'captions: {highlight_active_word: false}\n')
    segment = word_segment('Build a successful business.'.split())
    document = ass_for_window([segment], 0, 2, 1080, 1920, 'colorized', settings=settings)
    assert all(r'\1c' not in row[9] for row in events(document))
    enabled = overlay(tmp_path, monkeypatch, 'captions: {highlight_active_word: true}\n')
    document = ass_for_window([segment], 0, 2, 1080, 1920, 'colorized', settings=enabled)
    assert any(r'\1c&H6BFF7C&' in row[9] for row in events(document))


def test_studio_style_emphasis_is_unchanged_by_the_pro_emphasis_families():
    segment = word_segment('He made $50,000 in 7 days'.split())
    rows = events(ass_for_window([segment], 0, 2, 1080, 1920, 'studio'))
    # Studio keeps its approved single-strongest-word accent behavior.
    text = ' '.join(row[9] for row in rows)
    assert r'{\1c&HF6DD55&}$50,000{\1c&HFFFFFF&}' in text
