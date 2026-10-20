import json
import uuid

from analytics.collectors import latest_performance
from app.repositories.database import timestamp
from app.repositories.store import encode


def create_experiment(store, source_moment_id, name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 300:
        raise ValueError('Experiment needs a bounded name')
    identifier = str(uuid.uuid4())
    with store.connection(write=True) as db:
        db.execute('INSERT INTO experiments VALUES (?,?,?,?)', (identifier, source_moment_id, name.strip(), timestamp()))
    return identifier


def add_variant(store, experiment_id, clip_id, variant, settings):
    if not isinstance(variant, str) or not 1 <= len(variant) <= 80 or not isinstance(settings, dict):
        raise ValueError('Variant needs a label and recorded settings')
    with store.connection(write=True) as db:
        experiment = db.execute('SELECT source_moment_id FROM experiments WHERE id=?', (experiment_id,)).fetchone()
        clip = db.execute('SELECT moment_id FROM clips WHERE id=?', (clip_id,)).fetchone()
        if experiment is None or clip is None or experiment['source_moment_id'] != clip['moment_id']:
            raise ValueError('Variant must belong to the experiment source moment')
        db.execute('INSERT INTO experiment_variants VALUES (?,?,?,?,?)',
                   (str(uuid.uuid4()), experiment_id, clip_id, variant, encode(settings)))


def compare_variants(store, experiment_id):
    observations = latest_performance(store)
    with store.connection() as db:
        rows = db.execute('SELECT * FROM experiment_variants WHERE experiment_id=?', (experiment_id,)).fetchall()
    return {'experiment_id': experiment_id, 'variants': [dict(variant=row['variant'], clip_id=row['clip_id'],
        settings=json.loads(row['settings']), performance=[item.model_dump(mode='json') for item in observations
        if item.clip_id == row['clip_id']]) for row in rows],
        'note': 'Observed outcomes only. A single clip per variant does not establish causal superiority.'}
