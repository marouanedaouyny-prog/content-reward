"""ASS caption styles using the source transcript's existing word timing."""

import re

from clipping.captions import caption_words, cues_for_window
from clipping.template import STYLED_CAPTION_STYLES

# PRD-GROWTH section 17 emphasis families for the gold `pro` style: numbers,
# money, results, strong emotions, surprise/conflict and established keyword
# emphasis. Spans describe the displayed words; they never add new claims.
EMPHASIS = re.compile(
    r'\$\s?\d[\d,]*(?:\.\d+)?'
    r'|\b\d[\d,.]*(?:\.\d+)?\b'
    r'|\b\d+(?:\.\d+)?\s?(?:percent|%)\b'
    r'|\b(?:million|billion|thousand|dollars|money|revenue|profit|paid|earned|cost|price)\b'
    r'|\b(?:never|always|impossible|nobody|secret|mistake|biggest|worst|best|only)\b'
    r'|\b(?:business|successful|home|work|office|ideas)\b'
    r'|\b(?:shocking|unbelievable|insane|crazy|amazing|furious|terrified|heartbroken|excited|angry|disgusting)\b'
    r'|\b(?:scam|lied|exposed|backlash|conflict|fight|war)\b'
    r'|\b(?:won|winner|lost|failed|succeeded|beat|crushed|destroyed|bankrupt|millionaire)\b',
    re.IGNORECASE)


def ass_time(seconds):
    value = round(seconds * 100)
    return f'{value // 360000}:{value // 6000 % 60:02}:{value // 100 % 60:02}.{value % 100:02}'


def literal(text):
    # Full-width literal glyphs prevent transcript text becoming ASS commands.
    return (text.replace('\\', '\uff3c').replace('{', '\uff5b').replace('}', '\uff5d')
            .replace('\r', '').replace('\n', r'\N'))


def painted(text, spans, accent, base, uppercase=False):
    def display(value):
        return literal(value.upper() if uppercase else value)

    parts, offset = [], 0
    for start, end in spans:
        parts.extend((display(text[offset:start]), '{\\1c&H' + accent + '&}',
                      display(text[start:end]), '{\\1c&H' + base + '&}'))
        offset = end
    parts.append(display(text[offset:]))
    return ''.join(parts)


def ass_for_window(segments, start, duration, width, height, style, *, settings=None, time_map=None):
    from app.core.config import load_settings
    settings = settings or load_settings()
    if style not in STYLED_CAPTION_STYLES:
        raise ValueError('Choose colorized, pro, or studio caption style')
    # time_map shifts every timestamp through a silence-removal plan so burned
    # captions stay synchronized with the shortened clip.
    map_time = time_map or (lambda value: value)
    colorful = style == 'colorized'
    base, accent = ('FFFFFF', '6BFF7C') if colorful else ('F3F3EE', '5FC8F6')
    if style == 'studio':
        base, accent = 'FFFFFF', 'F6DD55'
    font_size = round(min(width / 1080, height / 1920) * (78 if colorful else 68))
    margin_x, margin_y = round(width * .09), round(height * .18)
    header = (
        '[Script Info]\nScriptType: v4.00+\n'
        f'PlayResX: {width}\nPlayResY: {height}\n'
        'ScaledBorderAndShadow: yes\nWrapStyle: 2\n\n[V4+ Styles]\n'
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, '
        'BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, '
        'BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Caption,Arial,{font_size},&H00{base},&H00{base},&H00141414,&H90000000,'
        f'-1,0,0,0,100,100,0,0,1,{4 if colorful else 3},2,2,{margin_x},{margin_x},{margin_y},1\n\n'
        '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    )
    words = []
    for segment in segments:
        within = [word for word in segment.get('words', [])
                  if word['start'] < start + duration and (word['end'] > start
                     or word['start'] == word['end'] and word['start'] >= start)]
        words.extend(caption_words(within))
    lines = []

    def event(begin, finish, text):
        begin, finish = map_time(begin), map_time(finish)
        if round(finish * 100) > round(begin * 100):
            lines.append(f'Dialogue: 0,{ass_time(begin)},{ass_time(finish)},Caption,,0,0,0,,{text}')

    highlight_active = bool(settings.captions.highlight_active_word) and style in ('colorized', 'studio')
    for cue in cues_for_window(segments, start, duration, settings=settings):
        text, begin, finish = cue['text'], cue['start'], cue['end']
        if style == 'pro':
            spans = [(match.start(), match.end()) for match in EMPHASIS.finditer(text)]
            event(begin, finish, painted(text, spans, accent, base))
            continue
        aligned, offset = [], 0
        for word in words:
            word_start, word_end = max(begin, word['start'] - start), min(finish, word['end'] - start)
            if word_start >= word_end:
                continue
            pattern = r'\s+'.join(re.escape(part) for part in word['word'].split())
            match = re.search(pattern, text[offset:]) if pattern else None
            if match:
                span = (offset + match.start(), offset + match.end())
                aligned.append((word_start, word_end, span))
                offset = span[1]
        if style == 'studio':
            excluded = {'their', 'there', 'these', 'those', 'would', 'could', 'should', 'about', 'because', 'which'}
            important = [(match.start(), match.end()) for match in re.finditer(r"\b[\w']{5,}\b|\b\d+\b", text)
                         if match.group().lower() not in excluded]
            important = sorted(important, key=lambda span: span[1] - span[0], reverse=True)[:1]
            aligned = [(word_start, word_end, word_span) for word_start, word_end, word_span in aligned
                       if any(word_span[0] < span_end and word_span[1] > span_start
                              for span_start, span_end in important)]
            if not words:
                event(begin, finish, painted(text, important, accent, base))
                continue
        boundaries = sorted({begin, finish,
                             *(boundary for word_start, word_end, _ in aligned for boundary in (word_start, word_end))})
        for event_start, event_end in zip(boundaries, boundaries[1:]):
            middle = (event_start + event_end) / 2
            active = next((span for word_start, word_end, span in aligned
                           if word_start <= middle < word_end), None) if highlight_active else None
            event(event_start, event_end, painted(text, [active] if active else [], accent, base, uppercase=colorful))
    return header + '\n'.join(lines) + '\n'
