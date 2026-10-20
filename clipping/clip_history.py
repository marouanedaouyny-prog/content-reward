"""Read durable interval reservations from prior clipping orders."""

import json
import re


def reservations(orders, current_id):
    records = []
    for manifest in orders.glob('*/order.json'):
        if manifest.parent.name == current_id:
            continue
        state = json.loads(manifest.read_text(encoding='utf-8'))
        moments = state.get('moments', [])
        for index, entry in enumerate(state.get('clip_entries', [])):
            if not entry.get('job_id') and not entry.get('source_clip_plan'):
                continue
            source = entry.get('source') or state.get('source_selection') or {}
            moment = entry.get('moment') or (moments[index] if index < len(moments) else {})
            plan = entry.get('source_clip_plan') or moment.get('clip_plan')
            if source.get('id') and plan:
                records.append({'source_id': source['id'], 'clip_plan': plan,
                                'source_excerpt': moment.get('source_excerpt', ''), 'order_id': state['id']})
    return records


def repeated_takeaway(excerpt, records):
    def shingles(text):
        words = re.findall(r"[a-z0-9']+", text.lower())
        if len(words) < 4:
            return set()
        return {tuple(words[index:index + 4]) for index in range(len(words) - 3)}

    current = shingles(excerpt)
    if not current:
        return False
    for record in records:
        previous = shingles(record.get('source_excerpt', ''))
        if previous and len(current & previous) / len(current | previous) >= .8:
            return True
    return False
