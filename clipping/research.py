"""Bounded metadata samples and descriptive cohorts; no outcome prediction."""

import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

MAX_BYTES = 25 * 1024 * 1024
MAX_RECORDS = 100_000
MIN_COHORT = 10
BRIEF_NOTE = ('Use this as a length/topic experiment from a historical sample, not a viral prediction. '
              'Source context, campaign permission and the actual transcript still determine the cut.')
LIMITATIONS = [
    'Historical snapshots: these counts do not measure current trends or view velocity.',
    'Compare rows within similar posting-date, language and country cohorts.',
    'Country/language labels and the sample may be incomplete or inaccurate.',
    'Associations do not establish causes or predict results for a new account.',
    'Campaign eligibility, music rights and reward terms require separate review.',
]


def terms(text):
    if not isinstance(text, str) or len(text) > 200:
        raise ValueError('Keywords must be text, at most 200 characters')
    return list(dict.fromkeys(term.strip().casefold() for term in text.split(',') if term.strip()))[:10]


def matches(text, term):
    return bool(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text.casefold()))


def integer(value):
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        raise ValueError('Expected a nonnegative integer')
    number = int(value)
    if number > 2**64 - 1:
        raise ValueError('Integer exceeds uint64')
    return number


def normalize(row):
    if not isinstance(row, dict):
        raise ValueError('Each record must be an object')
    identifier = str(integer(row['content_id']))
    date = datetime.fromisoformat(str(row['create_time']).replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Posting timestamp needs a timezone')
    date = date.astimezone(timezone.utc)
    duration = integer(row['duration'])
    if not 1 <= duration <= 65535:
        raise ValueError('Duration must be positive seconds')
    caption = row.get('desc') or ''
    if not isinstance(caption, str) or len(caption) > 4000:
        raise ValueError('Caption must be text, at most 4000 characters')
    result = {'id': identifier, 'month': date.strftime('%Y-%m'), 'duration': duration,
              'desc': caption, 'language': str(row.get('language') or 'unknown').lower()[:12],
              'country': str(row.get('country') or 'unknown').upper()[:12],
              'is_video': integer(row.get('is_video', 1)), 'is_ad': integer(row.get('is_ad', 0))}
    if result['is_video'] not in (0, 1) or result['is_ad'] not in (0, 1):
        raise ValueError('Video and advertising flags must be 0 or 1')
    result['views'] = integer(row['views'])
    result.update({field: integer(row[field]) if row.get(field) not in (None, '') else None
                   for field in ('likes', 'comments', 'shares', 'saves')})
    return result


def csv_records(text):
    try:
        yield from csv.DictReader(io.StringIO(text))
    except csv.Error as exc:
        raise ValueError('Invalid CSV sample: check the columns and individual field sizes') from exc


def planning_brief(cohorts, source):
    """Select one reproducible experiment, without comparing unlike audiences/dates."""
    contexts = defaultdict(list)
    for item in cohorts:
        if item['language'] == 'unknown' or item['country'] == 'UNKNOWN' or item['median_duration'] > 180:
            continue
        contexts[(item['month'], item['language'], item['country'])].append(item)
    if not contexts:
        return None, ('A brief needs at least ten posts with known language/country labels '
                      'and a typical length of 1–180 seconds. Import a suitable sample or adjust filters.')
    # Largest single cohort, not summed counts: topic matches may overlap.
    # A tie uses the latest posting month, then stable label ordering.
    context = sorted(contexts, key=lambda key: (key[1], key[2]))
    key = max(context, key=lambda key: (max(item['count'] for item in contexts[key]), key[0]))
    candidates = contexts[key]
    measured = [item for item in candidates if item['share_observations'] >= MIN_COHORT]
    support_order = lambda item: (-item['count'], abs(item['median_duration'] - 30), item['topic'], item['duration_min'])
    basis = 'sample_support'
    if len(measured) >= 2 and len({item['median_share_rate'] for item in measured}) > 1:
        chosen = sorted(measured, key=lambda item: (-item['median_share_rate'], *support_order(item)))[0]
        basis = 'share_rate'
        reason = (f"Highest median share/view ratio among {len(measured)} measured groups within "
                  f"{key[0]} / {key[1]} / {key[2]}. Each has at least ten measured positive-view posts.")
    else:
        chosen = sorted(candidates, key=support_order)[0]
        reason = ('Use the best-supported group in the selected context. There are not two groups '
                  'with distinct share/view ratios and at least ten measured posts each; no performance winner is inferred.')
    return {'topic': chosen['topic'], 'keywords': [] if chosen['topic'] == 'all matched posts' else [chosen['topic']],
            'target_duration': chosen['median_duration'], 'month': key[0], 'language': key[1], 'country': key[2],
            'support_count': chosen['count'], 'compared_cohorts': len(measured) if basis == 'share_rate' else len(candidates),
            'basis': basis, 'median_share_rate': chosen['median_share_rate'], 'can_apply': source != 'synthetic_demo',
            'reason': reason, 'note': BRIEF_NOTE}, (
                'Context selected by its largest supported group; equal support uses the latest posting month. '
                'This is a default experiment for this sample, not a ranking of all niches or countries.')


def analyze_metadata(content, filename, keywords='', country='', language='', source='operator_sample'):
    if len(content) > MAX_BYTES:
        raise ValueError('Metadata sample exceeds 25 MB')
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.csv', '.jsonl', '.ndjson'):
        raise ValueError('Upload CSV or JSONL; export a bounded Parquet sample first')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Metadata sample must be UTF-8 text') from exc
    if suffix == '.csv':
        records = csv_records(text)
    else:
        records = (line for line in text.splitlines() if line.strip())
    groups, seen = defaultdict(list), set()
    counts = {'input_records': 0, 'valid_records': 0, 'invalid_records': 0,
              'duplicate_records': 0, 'matched_records': 0, 'empty_captions': 0}
    selected = terms(keywords)
    for raw in records:
        counts['input_records'] += 1
        if counts['input_records'] > MAX_RECORDS:
            raise ValueError('Metadata sample exceeds 100,000 records')
        try:
            row = normalize(json.loads(raw) if isinstance(raw, str) else raw)
        except (ValueError, KeyError, TypeError, OverflowError):
            counts['invalid_records'] += 1
            continue
        if row['id'] in seen:
            counts['duplicate_records'] += 1
            continue
        seen.add(row['id'])
        counts['valid_records'] += 1
        counts['empty_captions'] += not bool(row['desc'].strip())
        if not row['is_video'] or row['is_ad']:
            continue
        if country and row['country'] != country.upper():
            continue
        if language and row['language'] != language.lower():
            continue
        topics = [term for term in selected if matches(row['desc'], term)] if selected else ['all matched posts']
        if not topics:
            continue
        counts['matched_records'] += 1
        lower = (row['duration'] // 15) * 15
        for topic in topics:
            groups[(topic, row['month'], row['language'], row['country'], lower)].append(row)
    if not counts['input_records']:
        raise ValueError('Sample contains no records')
    if not counts['valid_records']:
        raise ValueError('No valid records: need content_id, create_time, duration and views')
    cohorts = []
    for (topic, month, lang, region, lower), rows in groups.items():
        if len(rows) < MIN_COHORT:
            continue
        positive = [row for row in rows if row['views'] > 0]
        shares = [row['shares'] / row['views'] for row in positive if row['shares'] is not None]
        saves = [row['saves'] / row['views'] for row in positive if row['saves'] is not None]
        cohorts.append({'topic': topic, 'month': month, 'language': lang, 'country': region,
                        'duration_min': max(1, lower), 'duration_max': lower + 14, 'count': len(rows),
                        'median_duration': median(row['duration'] for row in rows),
                        'median_views': median(row['views'] for row in rows),
                        'share_observations': len(shares), 'save_observations': len(saves),
                        'median_share_rate': median(shares) if shares else None,
                        'median_save_rate': median(saves) if saves else None})
    cohorts.sort(key=lambda item: (-item['count'], item['topic'], item['month'], item['duration_min']))
    brief, brief_note = planning_brief(cohorts, source)
    return {**counts, 'source': source, 'keywords': selected, 'minimum_cohort_size': MIN_COHORT,
            'planning_brief': brief, 'brief_note': brief_note,
            'supported_cohorts': len(cohorts), 'cohorts': cohorts[:300], 'limitations': LIMITATIONS,
            'note': 'Descriptive research. Cohorts are ordered by support, not predicted virality. '
                    'Overlapping keywords can include the same post in multiple cohorts.'}


def demo_report():
    rows = []
    for topic in ('AI', 'gaming', 'interview'):
        for duration in (20, 35, 50):
            for index in range(10):
                rows.append({'content_id': str(1000 + len(rows)), 'create_time': '2025-08-01T12:00:00Z',
                             'desc': f'Synthetic {topic} demonstration', 'duration': duration,
                             'views': 100 + index * 10, 'shares': index, 'saves': index + 1,
                             'language': 'en', 'country': 'US'})
    content = '\n'.join(json.dumps(row) for row in rows).encode()
    return analyze_metadata(content, 'demo.jsonl', keywords='AI,gaming,interview', source='synthetic_demo')
