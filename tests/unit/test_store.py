import json
import sqlite3
import uuid

import pytest


def state():
    return {'id': str(uuid.uuid4()), 'created_at': '2026-10-20T00:00:00+00:00',
            'status': 'created', 'stage': 'preflight', 'config': {}, 'clip_entries': []}


def test_migrations_are_repeatable_and_preserve_existing_job_tables(tmp_path):
    from app.repositories.store import Store
    path = tmp_path / 'domain.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE clipping_job(id TEXT PRIMARY KEY)')
        db.execute("INSERT INTO clipping_job VALUES ('old-job')")
    Store(path)
    store = Store(path)
    with store.connection() as db:
        assert db.execute('SELECT id FROM clipping_job').fetchone()[0] == 'old-job'
        assert db.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] >= 1
        assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'orders', 'sources', 'candidate_moments', 'clips', 'campaigns', 'publications',
            'performance_metrics', 'rewards', 'pipeline_events', 'experiments'} <= names


def test_database_order_survives_broken_or_stale_json_export(tmp_path):
    from app.repositories.store import Store
    store = Store(tmp_path / 'domain.db')
    order = state()
    store.save_order(order)
    folder = tmp_path / 'orders' / order['id']
    folder.mkdir(parents=True)
    manifest = folder / 'order.json'
    manifest.write_text(json.dumps({**order, 'status': 'failed'}))
    store.import_orders(tmp_path / 'orders')
    assert store.get_order(order['id'])['status'] == 'created'
    manifest.write_text('{broken')
    assert store.latest_order()['id'] == order['id']


def test_historical_import_is_idempotent_and_invalid_documents_are_quarantined(tmp_path):
    from app.repositories.store import Store
    order = state()
    folder = tmp_path / 'orders' / order['id']
    folder.mkdir(parents=True)
    (folder / 'order.json').write_text(json.dumps(order))
    bad = tmp_path / 'orders' / str(uuid.uuid4())
    bad.mkdir()
    (bad / 'order.json').write_text('{')
    store = Store(tmp_path / 'domain.db')
    store.import_orders(tmp_path / 'orders')
    store.import_orders(tmp_path / 'orders')
    assert len(store.list_orders()) == 1
    assert store.import_warnings()


def test_order_optimistic_lock_refuses_stale_writer(tmp_path):
    from app.repositories.store import Store
    store = Store(tmp_path / 'domain.db')
    order = state()
    revision = store.save_order(order)
    store.save_order({**order, 'status': 'running'}, expected_revision=revision)
    with pytest.raises(ValueError, match='changed'):
        store.save_order({**order, 'status': 'failed'}, expected_revision=revision)
