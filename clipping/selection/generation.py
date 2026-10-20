"""Merge independent transcript and metadata anchors by their source cue index."""

import bisect
import math
import re

from clipping.research import matches


def candidate_starts(segments, keywords, replay, chapters=(), timed_energy=(), timed_engagement=()):
    starts = [segment['start'] for segment in segments]
    anchors = {index: {'transcript_boundary'} for index in range(len(segments))}
    for index, segment in enumerate(segments):
        text = segment['text']
        if '?' in text and re.match(r'^(?:what|why|how|when|where|who|which|can|could|should|would|is|are|do|does|did|have|has)\b',
                                     text, re.IGNORECASE):
            anchors[index].add('question_answer')
        if any(matches(text, term) for term in keywords):
            anchors[index].add('keyword')
        if index and re.search(r'[.!?]["\u201d\u2019\]\)]*$', segments[index - 1]['text'].rstrip()):
            anchors[index].add('sentence_boundary')

    def add_time(value, strategy):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return
        index = max(0, bisect.bisect_right(starts, value) - 1)
        if value <= segments[index]['end']:
            anchors[index].add(strategy)

    for index, item in enumerate(replay):
        previous = replay[index - 1]['value'] if index else -1
        following = replay[index + 1]['value'] if index + 1 < len(replay) else -1
        if item['value'] >= previous and item['value'] >= following:
            add_time((item['start_time'] + item['end_time']) / 2, 'replay_peak')
    for chapter in chapters or ():
        if isinstance(chapter, dict):
            add_time(chapter.get('start_time'), 'chapter')
    for records, strategy in ((timed_energy, 'measured_energy'), (timed_engagement, 'timed_engagement')):
        for record in records or ():
            if isinstance(record, dict) and record.get('observed') is True:
                add_time(record.get('start_time'), strategy)
    return anchors
