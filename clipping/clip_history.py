"""Read durable interval reservations from prior clipping orders."""

import json

from clipping.selection.dedup import compare_moments
from app.core.config import load_settings


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


def repeated_takeaway(excerpt, records, *, settings=None):
    settings = settings or load_settings()
    return any(compare_moments({'source_excerpt': excerpt}, record, settings=settings)['duplicate']
               for record in records)
