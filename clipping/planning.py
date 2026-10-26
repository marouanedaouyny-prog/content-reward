"""Explainable source-window suggestions; scores are editorial, not predictions."""

import json
import math
import re
import subprocess
from urllib.parse import parse_qs, urlparse

from clipping.media import validate_segments
from clipping.research import matches, terms
from app.core.config import load_settings
from clipping.selection.generation import candidate_starts
from clipping.selection.scoring import score_candidate
from growth.scorer import GrowthScorer

NOTE = 'Transcript heuristics suggest complete moments for review. No trained virality model or forecast is used.'
REPLAY_NOTE = ('Selected using YouTube replay intensity and source transcript boundaries. '
               'Replay intensity is relative within this video, not a prediction of clip views.')
PROMOTION = re.compile(
    r'\b(?:sponsored by|sponsoring (?:the|this|our)|our sponsor|promo code|use code|'
    r'link in the description|free trial|your first order)\b'
    r'|\b(?:in theaters|stream (?:it |this )?now|tickets (?:are )?(?:on sale|available)|'
    r'buy (?:your )?tickets|take a (?:short )?break|after (?:the|this) break)\b'
    r'|\b(?:get|save|take)\s+\$\s*\d+(?:\.\d+)?\s+off\b'
    r'|\b(?:visit|go to|check out)\s+[a-z0-9-]+\.com\b'
    r'|\b(?:i|we) (?:want|need|ask) you to subscribe\b'
    r'|\b(?:hit|click|press|smash) (?:the|that|our) subscribe button\b'
    r'|\b[a-z0-9-]+\.com\s*(?:/|slash\b)', re.IGNORECASE)
NON_SPEECH = re.compile(
    r'\[(?:music|applause|laughter|laughs?|laughing|cheering|cheers|inaudible|silence|crosstalk)\]',
    re.IGNORECASE)
INTRO_OUTRO = re.compile(
    r"\b(?:what['’]s up (?:everybody|everyone)|welcome (?:to|back)|our guest today|"
    r'ladies and gentlemen|thanks? for (?:watching|listening|joining)|'
    r'(?:subscribe|like and subscribe) to (?:our|the|my) channel|see you (?:next|in the next)|'
    r'closing tradition|last guest leaves a question|thank you (?:so much )?for '
    r'(?:being|your time|taking (?:the|your) time)|generous with your time)\b',
    re.IGNORECASE)
EXCLUDED_CHAPTER_LABELS = frozenset({
    'intro', 'introduction', 'outro', 'sponsor', 'sponsors', 'sponsorship',
    'sponsor segment', 'sponsored segment', 'ad', 'ads', 'ad break', 'advert',
    'advert break', 'advertisement', 'advertisements', 'advertising',
    'commercial', 'commercial break',
})


def excluded_chapter_ranges(chapters, source_duration=None):
    """Use explicit whole chapter labels; topic titles are not introductions or ads."""
    if not isinstance(chapters, list):
        return []
    limit = (source_duration if not isinstance(source_duration, bool)
             and isinstance(source_duration, (int, float)) and math.isfinite(source_duration)
             and source_duration > 0 else None)
    ranges = []
    for chapter in chapters:
        if not isinstance(chapter, dict) or not isinstance(chapter.get('title'), str):
            continue
        title = ' '.join(chapter['title'].casefold().split()).rstrip(':.')
        start, end = chapter.get('start_time'), chapter.get('end_time')
        if (title not in EXCLUDED_CHAPTER_LABELS
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in (start, end))
                or not 0 <= start < end or limit is not None and end > limit + .25):
            continue
        ranges.append({'title': chapter['title'], 'start_time': start, 'end_time': end})
    return ranges


def _chapter_overlaps(start, end, ranges):
    return [chapter for chapter in ranges if start < chapter['end_time'] and end > chapter['start_time']]


def chapter_conflicts(plan, chapters, *, source_duration=None):
    """Compare immutable source coordinates, never section-local render offsets."""
    ranges = excluded_chapter_ranges(chapters, source_duration)
    if not ranges:
        return []
    start, duration = plan.get('start_seconds'), plan.get('duration_seconds')
    if (any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in (start, duration)) or start < 0 or duration <= 0
            or not math.isfinite(start + duration)):
        raise ValueError('Chapter checks require a valid source clip window')
    return _chapter_overlaps(start, start + duration, ranges)


def speech_text(text):
    """Normalize caption display markers for scoring; never change source excerpts."""
    return ' '.join(NON_SPEECH.sub(' ', text.replace('>>', ' ')).split())


def opening_context(text, keywords=(), *, strict=True):
    """Detect observable references while retaining explicit subjects and impersonal hooks."""
    opening = re.split(r'(?<=[.!?])\s+', speech_text(text).replace('\u2019', "'"), maxsplit=1)[0]
    question = bool('?' in opening and re.match(
        r'^(?:what|why|how|when|where|who|which|can|could|should|would|is|are|do|does|did|have|has)\b',
        opening, re.IGNORECASE))
    subject = opening.split('?', 1)[0]
    explicit_topic = any(matches(subject, term) for term in keywords)
    named_demonstrative = bool(re.search(
        r'\b(?:this|that|these|those)\s+(?!(?:is|are|was|were|did|does|do|can|could|will|would|'
        r'come|comes|work|works|happen|happens|mean|means|feel|feels|make|makes|take|takes|go|goes)\b)[a-z]+',
        subject, re.IGNORECASE))
    impersonal_question = bool(re.match(
        r'^(?:why|how) (?:is|was) it (?:so |really |very )?(?:hard|easy|difficult|important|possible) to\b',
        subject, re.IGNORECASE))
    referential = bool(question and (re.match(r'^which one\b', subject, re.IGNORECASE)
        or re.search(r'\b(?:him|her|them|it)\b|\b(?:that|those|this|these)\s*$', subject, re.IGNORECASE)
        or strict and re.search(r'\b(?:that|those|this|these)\b', subject, re.IGNORECASE))
        and not (explicit_topic or named_demonstrative or impersonal_question))
    statement = re.sub(r'^(?:i (?:suppose|guess|think|believe)|obviously|unfortunately|fortunately)\s*,?\s+',
                       '', opening, flags=re.IGNORECASE)
    impersonal = bool(re.match(r"^it(?: (?:is|was|can be|would be)|'s) .+\b(?:to|that)\b",
                               statement, re.IGNORECASE))
    explanation = re.match(r"^(?:this|that|it)(?: is|'s) (?:why|how) (.+)", statement, re.IGNORECASE)
    if explanation:
        content = set(re.findall(r'[a-z]{3,}', explanation[1].lower())) - {
            'this', 'that', 'they', 'them', 'does', 'happens', 'happen', 'works', 'work', 'because'}
        impersonal = impersonal or len(content) >= 2
    unseen = bool(re.match(
        r"^(?:it|that|this|they|he|she|those|these)(?:(?:'s|'re|'ve|'d|'ll)\b|"
        r"(?:\s+(?:both|all|also|even|still|just|really|never|always))?\s+"
        r"(?:is|isn't|are|aren't|was|wasn't|were|weren't|did|didn't|does|doesn't|"
        r"has|hasn't|have|haven't|had|hadn't|will|won't|would|wouldn't|can|can't|could|couldn't|means?|happened)\b)",
        statement, re.IGNORECASE)) and not impersonal
    linked = bool(re.match(r'^(?:and|but|so|because|then|also)\b', opening, re.IGNORECASE))
    return referential or unseen or linked


def host_meta_setup(text):
    text = speech_text(text).replace('\u2019', "'")
    return bool(re.search(
        r"\bmy line of questioning\b|\bwe(?:'ve| have)? (?:got|have|received) (?:another |a |the next )?"
        r"(?:voice note|listener (?:message|question)|caller)\b", text, re.IGNORECASE))


def _needs_payoff(text):
    """Punctuation alone cannot finish an announced answer or host setup."""
    # Every alternative ends at the final ASCII sentence terminator and cannot
    # cross an earlier one. Avoid rescanning complete earlier sentences for
    # every overlapping candidate, while keeping unfinished cue fragments.
    last = max(text.rfind('.'), text.rfind('!'), text.rfind('?'))
    if last >= 0:
        previous = max(text.rfind('.', 0, last), text.rfind('!', 0, last),
                       text.rfind('?', 0, last))
        text = text[previous + 1:]
    return bool(re.search(
        r"(?:let me tell you what|here['’]s (?:the thing|what)|my (?:line of )?question(?:ing)?[^.!?]*|"
        r"(?:it['’]s|it is) (?:really )?(?:just )?to (?:understand|know)[^.!?]*|"
        r"(?:i|we) (?:want|would like|am trying|are trying) to (?:understand|know)[^.!?]*)"
        r'''[.!?]["'”’»」』）)\]}]*$''', text, re.IGNORECASE))


def _weak_standalone_opening(text):
    return bool(re.match(
        r"^(?:(?:yes(?: sir)?|no|i agree|i like it|me too|that['’]s right)[,;:.!?]|"
        r"i (?:was|am|did|had|have|would|could|can|do|will)(?: not|n['’]t)?[,;:.!?]|"
        r"(?:why|how so|what(?:['’]s| is)? next|what happened|did you know)\s*\?|"
        r"i think i['’]m going to do (?:this|that)\b|"
        r'(?:one|some|another) of (?:those|these|the) (?:moments|things|times)\b)',
        text, re.IGNORECASE))


def post_caption(excerpt):
    """Keep complete spoken sentences within the post-caption budget."""
    text = speech_text(str(excerpt or ''))
    sentences = re.findall(r'''.+?[.!?]["'”’»」』）)\]}]*(?=\s|$)''', text)
    chosen = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not chosen and len(sentence) > 220:
            continue
        if len(' '.join([*chosen, sentence])) > 220:
            break
        chosen.append(sentence)
    return ' '.join(chosen) if chosen else 'Watch this moment from the original conversation.'


def _excluded_intervals(plans, source_duration):
    intervals = []
    for plan in plans or ():
        if not isinstance(plan, dict):
            raise ValueError('Excluded windows must contain clip plans')
        start, duration = plan.get('start_seconds'), plan.get('duration_seconds')
        if (any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in (start, duration)) or start < 0 or duration <= 0
                or start + duration > source_duration + .25):
            raise ValueError('Excluded window has invalid source boundaries')
        intervals.append((start, start + duration))
    return intervals


def usable_heatmap(value, duration):
    """Keep only finite, ordered YouTube bins; unknown or flat data is not evidence."""
    if not isinstance(value, list) or not 2 <= len(value) <= 1000:
        return []
    bins, previous = [], 0
    for item in value:
        if not isinstance(item, dict):
            return []
        start, end, intensity = (item.get(key) for key in ('start_time', 'end_time', 'value'))
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
               for v in (start, end, intensity)):
            return []
        if not previous <= start < end <= duration + .25 or not 0 <= intensity <= 1:
            return []
        bins.append({'start_time': start, 'end_time': end, 'value': intensity})
        previous = end
    return bins if max(b['value'] for b in bins) > min(b['value'] for b in bins) else []


def sentence_ending(text):
    # Quoted dialogue can end in a closing quote/bracket after its punctuation.
    return bool(re.search(r'''[.!?。！？]["'”’»」』）)\]}]*$''', text.rstrip()))


def filler_opening(text):
    text = speech_text(text)
    value = ' '.join(re.findall(r"[a-z']+", text.lower()))
    exact = value in {
        'you know what i mean', 'do you know what i mean', 'know what i mean',
        'you know', 'i mean', 'right', 'okay', 'ok', 'yeah', 'yes', 'exactly',
        "that's right", "that's just life right",
        "we're going", 'here we go', "let's go", 'you get me', 'mhm', 'mm hmm', 'uh huh',
    }
    prefixed = re.match(r"^\s*(?:you know(?: what i mean)?|i mean|okay|ok|yeah|right|all right|well|um|uh|"
                        r"what (?:do )?you mean|like that)\s*[,;:.!?]", text,
                        re.IGNORECASE)
    linked = re.match(r'^(?:right|okay|ok|yeah|well) (?:so|and|but)\b', value)
    return bool(exact or prefixed or linked or value.startswith('you know what i mean '))


def standalone_boundary_checks(text):
    """Recheck current text policy without changing a saved source window."""
    text = speech_text(text)
    return {'no_filler_or_weak_opening': bool(text) and not filler_opening(text)
                and not _weak_standalone_opening(text),
            'no_pending_payoff': not _needs_payoff(text)}


def youtube_url(value):
    try:
        parsed = urlparse(value)
        if (parsed.scheme != 'https' or parsed.username or parsed.password
                or parsed.port not in (None, 443)):
            raise ValueError
        if parsed.hostname == 'youtu.be':
            identifier = parsed.path.strip('/')
        elif parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if parsed.path == '/watch':
                identifiers = parse_qs(parsed.query).get('v', [])
                identifier = identifiers[0] if len(identifiers) == 1 else ''
            else:
                match = re.fullmatch(r'/(?:shorts|embed|live)/([\w-]{11})/?', parsed.path)
                identifier = match[1] if match else ''
        else:
            raise ValueError
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier):
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Use a complete HTTPS YouTube video link with a valid video ID') from exc
    return f'https://www.youtube.com/watch?v={identifier}'


def inspect_youtube(value):
    from clipping import media
    url = youtube_url(value)
    try:
        info = json.loads(media.command([*media.ytdlp_command(), '--ignore-config', '--skip-download',
            '--dump-single-json', '--no-playlist', '--no-warnings', '--socket-timeout', '10',
            '--retries', '1', url], timeout=45))
        if not isinstance(info, dict):
            raise ValueError('Expected video metadata')
        duration = float(info.get('duration') or 0)
        if not math.isfinite(duration) or duration <= 0 or info.get('is_live'):
            raise ValueError('Choose a recorded video with a known duration')
    except (ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        raise ValueError('YouTube details unavailable. Check the link, network access and yt-dlp; '
                         'you can still use an authorized uploaded source.') from exc
    return {'url': url, 'title': str(info.get('title') or 'Untitled video')[:300],
            'creator': str(info.get('uploader') or info.get('channel') or '')[:200],
            'duration': duration, 'note': 'Public metadata does not establish permission to clip this source.'}


def _ranking_report(candidate, settings, *, rank_by_growth, feedback):
    growth = candidate['growth']
    use_growth = rank_by_growth and growth['evidence_coverage'] > 0
    base = growth['score'] if use_growth else candidate['selection']['score']
    adjustment = 0.0
    if feedback is not None:
        observed = feedback(candidate)
        samples = observed.get('samples', 0)
        supported = (observed.get('supported') is True and isinstance(samples, int)
                     and not isinstance(samples, bool) and samples >= settings.feedback.minimum_samples)
        value = observed.get('adjustment', 0)
        if supported:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Supported feedback adjustment must be a finite number')
            maximum = settings.feedback.maximum_adjustment
            adjustment = max(-maximum, min(maximum, value))
        candidate['feedback'] = {**observed, 'supported': supported, 'adjustment': adjustment,
                                 'original_score': base, 'adjusted_score': max(0, min(1, base + adjustment))}
    return {'basis': 'configured_growth_score' if use_growth else 'selection_score',
            'base_score': base, 'feedback_adjustment': adjustment,
            'score': max(0, min(1, base + adjustment)),
            'growth_evidence_coverage': growth['evidence_coverage'],
            'note': 'Editorial ranking before overlap pruning; this is not a probability of future views.'}


def suggest_cuts(segments, source_duration, target_duration=30, min_duration=15,
                 max_duration=60, keywords='', heatmap=None, *, limit=3, min_gap=None,
                 excluded_windows=None, require_standalone=False, settings=None,
                 source=None, chapters=None, rank_by_growth=False, feedback=None):
    settings = settings or load_settings()
    weights = settings.selection.editorial
    growth_scorer = GrowthScorer(settings)
    values = (source_duration, target_duration, min_duration, max_duration)
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in values):
        raise ValueError('Source and clip duration must be finite numbers')
    if source_duration <= 0 or not 1 <= min_duration <= max_duration <= 180:
        raise ValueError('Clip duration limits must satisfy 1 <= minimum <= maximum <= 180')
    if not isinstance(limit, int) or not 1 <= limit <= 20 or (min_gap is not None and
            (not isinstance(min_gap, (int, float)) or not math.isfinite(min_gap) or min_gap < 0)):
        raise ValueError('Invalid suggestion count or separation')
    segments = validate_segments(segments, source_duration)
    if any(current['start'] < previous['end'] for previous, current in zip(segments, segments[1:])):
        raise ValueError('Transcript cues overlap; merge overlapping subtitles before automatic planning')
    if len(segments) > 5000:
        raise ValueError('Transcript exceeds 5,000 segments; use a shorter source or merge subtitle cues')
    excluded = _excluded_intervals(excluded_windows, source_duration)
    selected_terms = terms(keywords)
    replay = usable_heatmap(heatmap, source_duration)
    source_chapters = chapters or (source or {}).get('chapters')
    excluded_chapters = excluded_chapter_ranges(source_chapters, source_duration) if require_standalone else []
    anchors = candidate_starts(segments, selected_terms, replay, source_chapters,
                               (source or {}).get('timed_energy'), (source or {}).get('timed_engagement'))
    target = max(min_duration, min(target_duration, max_duration))
    candidates = []
    for start_index, first in enumerate(segments):
        options, candidate_text = [], ''
        for end_index in range(start_index, min(len(segments), start_index + 150)):
            last = segments[end_index]
            duration = last['end'] - first['start']
            if duration > max_duration:
                break
            if require_standalone:
                candidate_text += ' ' + speech_text(last['text'])
            if duration >= min_duration:
                ending_text = speech_text(last['text'])
                question_end = bool(re.search(r'''\?["'”’)]*$''', ending_text))
                completed_end = sentence_ending(ending_text)
                empty_payoff = ' '.join(re.findall(r"[a-z']+", ending_text.lower())) in {
                    'yes', 'yeah', 'no', 'okay', 'ok', 'right', 'exactly', 'mhm', 'mm hmm',
                    'uh huh', 'wow', 'oh wow', "that's right", 'all right',
                }
                if require_standalone and (not completed_end or question_end or empty_payoff
                                           or _needs_payoff(candidate_text)):
                    continue
                if _chapter_overlaps(first['start'], last['end'], excluded_chapters):
                    continue
                gap = min_gap if min_gap is not None else 0
                if any(not (last['end'] + gap <= old_start or old_end + gap <= first['start'])
                       for old_start, old_end in excluded):
                    continue
                options.append((not completed_end, question_end,
                                abs(duration - target), end_index, duration))
        if not options:
            continue
        _, _, _, end_index, duration = min(options)
        window = segments[start_index:end_index + 1]
        excerpt = ' '.join(segment['text'].strip() for segment in window)
        opening, ending = speech_text(first['text']), speech_text(window[-1]['text'])
        question = bool('?' in opening and re.match(
            r'^(?:what|why|how|when|where|who|which|can|could|should|would|is|are|do|does|did|have|has)\b',
            opening, re.IGNORECASE))
        contextual = opening_context(opening, selected_terms, strict=require_standalone)
        referential = question and contextual
        linked_opening = bool(re.match(r'^(?:and|but|so|because|then|also)\b', opening, re.IGNORECASE))
        mid_sentence = bool(start_index and not sentence_ending(speech_text(segments[start_index - 1]['text'])))
        introductory = bool(INTRO_OUTRO.search(speech_text(excerpt)))
        host_setup = host_meta_setup(excerpt)
        promotional = bool(PROMOTION.search(speech_text(excerpt)))
        if require_standalone and (not opening or filler_opening(opening) or _weak_standalone_opening(opening)
                or contextual or linked_opening or mid_sentence or introductory or host_setup or promotional):
            continue
        speech = sum(segment['end'] - segment['start'] for segment in window)
        silence = max(0, duration - speech)
        largest_gap = max((current['start'] - previous['end']
                           for previous, current in zip(window, window[1:])), default=0)
        score, reasons = weights['baseline'], ['Starts and ends at subtitle boundaries']
        if filler_opening(opening):
            score -= weights['filler_penalty']
            reasons.append('Opening is a conversational filler; review the context')
        elif question and not referential:
            score += weights['question_bonus']
            reasons.append('Opening poses a question')
        if referential:
            score -= weights['referential_penalty']
            reasons.append('Opening question refers to unseen context; name its subject before using it')
        if mid_sentence:
            score -= weights['mid_sentence_penalty']
            reasons.append('Opening follows an unfinished source sentence; review the context')
        if re.search(r'\d|\b(?:one|two|three|step|steps)\b', excerpt, re.IGNORECASE):
            score += weights['concrete_bonus']
            reasons.append('Includes a concrete number or step')
        matched_terms = sum(matches(excerpt, term) for term in selected_terms)
        if matched_terms:
            score += weights['topic_bonus'] + min(weights['topic_extra_cap'], (matched_terms - 1) * weights['topic_extra'])
            reasons.append('Matches the source topic or niche keywords')
            opening_matches = sum(matches(opening, term) for term in selected_terms)
            if opening_matches:
                score += min(weights['opening_topic_cap'], opening_matches * weights['opening_topic_bonus'])
                reasons.append('Opening names the source topic')
        if promotional:
            score -= weights['promotion_penalty']
            reasons.append('Contains promotional language; review before selecting')
        completed = sentence_ending(ending)
        if completed:
            score += weights['completed_bonus']
            reasons.append('Ends at sentence-ending punctuation')
        else:
            reasons.append('No sentence ending was detected within the duration limits; review the context')
        if ending.rstrip().endswith('?'):
            score -= weights['question_ending_penalty']
            reasons.append('Ends with a question rather than its answer; review the payoff')
        if silence > 1:
            score -= min(weights['silence_cap'], silence * weights['silence_penalty'])
            reasons.append('Contains speech gaps; compare a more continuous moment')
        if linked_opening:
            score -= weights['linked_penalty']
            reasons.append('Opening may rely on previous context; review it')
        score -= min(weights['duration_cap'], abs(duration - target) * weights['duration_penalty'])
        suggestion = {'clip_plan': {'start_seconds': first['start'],
                           'duration_seconds': round(duration, 3), 'aspect_ratio': '9:16'},
                           'editorial_score': round(score, 1), 'score_type': 'editorial_heuristic',
                           'reasons': reasons, 'source_excerpt': excerpt[:2000],
                           'caption': post_caption(excerpt if require_standalone else opening), 'note': NOTE,
                           'strategies': sorted(anchors[start_index]),
                           'transcript_features': {'opening_question': question and not referential,
                               'opening_topic_matches': sum(matches(opening, term) for term in selected_terms),
                               'topic_matches': matched_terms, 'ending_question': ending.rstrip().endswith('?'),
                               'words_per_second': len(speech_text(excerpt).split()) / duration},
                           'quality': {'filler_opening': filler_opening(opening),
                               'context_dependent_opening': contextual,
                               'mid_sentence_opening': mid_sentence,
                               'intro_or_outro': introductory,
                               'host_meta_setup': host_setup,
                               'completed_ending': completed,
                               'ending_question': bool(re.search(r'''\?["'\u201d\u2019)]*$''', ending)),
                               'promotional': promotional,
                               'silence_seconds': round(silence, 3),
                               'largest_speech_gap': round(largest_gap, 3),
                               'speech_ratio': round(speech / duration, 3)}}
        if replay:
            start, end = first['start'], window[-1]['end']
            peak = max((bin['value'] for bin in replay
                        if start <= (bin['start_time'] + bin['end_time']) / 2 < end), default=0)
            average = sum(max(0, min(end, bin['end_time']) - max(start, bin['start_time']))
                          * bin['value'] for bin in replay) / duration
            suggestion.update(score_type='youtube_replay_heatmap', replay_score=round(average, 6),
                              replay_peak=peak, note=REPLAY_NOTE)
            reasons.insert(0, 'Compared with observed YouTube replay intensity for this window')
        suggestion['selection'] = score_candidate(suggestion, settings.selection, source=source)
        suggestion['growth'] = growth_scorer.score(suggestion, keywords=selected_terms, source=source)
        if rank_by_growth and require_standalone:
            from clipping.quality.validation import validate_candidate
            if (suggestion['selection']['score'] < settings.selection.minimum_score
                    or not validate_candidate(suggestion, minimum=min_duration, maximum=max_duration,
                                              settings=settings, strict=True).passed):
                continue
        suggestion['ranking'] = _ranking_report(suggestion, settings, rank_by_growth=rank_by_growth,
                                                feedback=feedback)
        candidates.append((completed, suggestion))
    candidates.sort(key=lambda item: (not item[0], -item[1]['ranking']['score'], -item[1]['selection']['score'],
        -item[1]['editorial_score'], item[1]['clip_plan']['start_seconds']))
    chosen = []
    for _, candidate in candidates:
        plan = candidate['clip_plan']
        start, end = plan['start_seconds'], plan['start_seconds'] + plan['duration_seconds']
        overlaps = False
        for previous in chosen:
            old = previous['clip_plan']
            old_start, old_end = old['start_seconds'], old['start_seconds'] + old['duration_seconds']
            intersection = max(0, min(end, old_end) - max(start, old_start))
            if (min_gap is not None and not (end + min_gap <= old_start or old_end + min_gap <= start)
                    or min_gap is None and intersection / min(end - start, old_end - old_start)
                    >= settings.dedup.timestamp_overlap_threshold):
                overlaps = True
        if not overlaps:
            chosen.append(candidate)
        if len(chosen) == limit:
            break
    if not chosen:
        raise ValueError('No complete transcript window fits the clip duration limits')
    return chosen


def prepare_clip_plan(data, output, folder, storage):
    transcript = json.loads((storage / output['transcript_path']).read_text(encoding='utf-8'))
    campaign, desired = data['campaign'], data['clip_plan']
    minimum = max(1, campaign.get('duration_min') or min(15, desired['duration_seconds']))
    maximum = min(180, campaign.get('duration_max') if campaign.get('duration_max') is not None
                  else max(60, desired['duration_seconds']))
    keywords = data.get('research_keywords', '')
    source_title = (output.get('source_selection') or {}).get('title', '')
    stopwords = {'this', 'that', 'these', 'those', 'from', 'with', 'what', 'when', 'where', 'which',
                 'why', 'who', 'how', 'you', 'your', "you're", "you've", "you'll", 'have', 'has',
                 'had', 'does', 'did', 'can', 'could', 'should', 'would', 'will', 'must', 'may',
                 'might', 'the', 'and', 'for', 'are', 'not', 'but', 'all', 'was', 'were', 'our',
                 'ours', 'there', 'here', 'than', 'then', 'its', "it's", 'been', 'being', 'some',
                 'just', 'more', 'most', 'only', 'very', 'ever', 'full', 'interview', 'podcast',
                 'episode', 'about', 'they', 'their', 'them', 'think', 'thinks', 'says', 'said'}
    title_terms = [word for word in re.findall(r"[a-zA-Z][a-zA-Z']{2,}", source_title.lower())
                   if word not in stopwords]
    keywords = ', '.join(dict.fromkeys([*terms(keywords), *title_terms]))[:200]
    suggestions = suggest_cuts(transcript['segments'], output['source_duration'],
                              desired['duration_seconds'], minimum, maximum,
                              keywords, output.get('source_heatmap'))
    for suggestion in suggestions:
        suggestion['clip_plan']['aspect_ratio'] = desired['aspect_ratio']
        if data.get('preview_only') and source_title:
            creator = (output.get('source_selection') or {}).get('creator')
            suggestion['caption'] = ' '.join(source_title.split()) + (
                '\n\nSource: ' + creator if creator else '')
    path = folder / 'clip-ideas.json'
    note = suggestions[0]['note']
    if suggestions[0]['score_type'] == 'editorial_heuristic' and data.get('source_url'):
        note = 'YouTube replay data unavailable. ' + note
    path.write_text(json.dumps({'suggestions': suggestions, 'note': note}, ensure_ascii=False, indent=2),
                    encoding='utf-8')
    return {'selected_clip_plan': suggestions[0]['clip_plan'], 'clip_suggestions': suggestions,
            'planning_origin': suggestions[0]['score_type'], 'planning_note': note,
            'ideas_path': path.relative_to(storage).as_posix()}
