"""Noninteractive chat launcher: fresh orders, safe resume and duplicate protection."""

import importlib
import json

import pytest

from clipping.orchestrator import Config, Controller, atomic_json, order_lock


def saved_order(storage, status='connection_unavailable', count=20):
    controller = Controller(storage, Config(provider='public', clip_count=count,
        partial_downloads=True, caption_style='colorized', clips_per_source=20), emit=lambda _: None)
    controller.update(status=status, completed_clip_count=7, requested_clip_count=count)
    return controller


def run_stub(monkeypatch):
    calls = []

    def run(controller, connection_attempts=3, retry_delay=5):
        calls.append((controller, connection_attempts, retry_delay))
        return {**controller.state, 'status': 'connection_unavailable',
                'reason': 'youtube_connection_unavailable'}

    monkeypatch.setattr(Controller, 'run', run)
    return calls


def result(capsys):
    return json.loads(capsys.readouterr().out.splitlines()[-1])


def test_empty_workspace_starts_twenty_colorized_clips_without_prompting(tmp_path, monkeypatch, capsys):
    calls = run_stub(monkeypatch)
    mod = importlib.import_module('clipping.autorun')
    assert mod.main(['--storage', str(tmp_path), '--connection-attempts', '1', '--retry-delay', '0']) == 75
    controller, attempts, delay = calls[0]
    assert (attempts, delay) == (1, 0)
    assert controller.config.clip_count == controller.config.clips_per_source == 20
    assert controller.config.caption_style == 'colorized' and controller.config.framing_mode == 'fit'
    assert controller.config.partial_downloads is True and controller.config.provider == 'public'
    summary = result(capsys)
    assert summary['mode'] == 'new' and summary['id'] == controller.state['id']
    assert summary['status'] == 'connection_unavailable' and summary['requested_clip_count'] == 20
    assert summary['clips'] == [] and summary['index'] is None


def test_default_resumes_existing_production_without_replacing_its_settings(tmp_path, monkeypatch, capsys):
    previous = saved_order(tmp_path, count=24)
    snapshot = previous.manifest.read_bytes()
    calls = run_stub(monkeypatch)
    mod = importlib.import_module('clipping.autorun')
    assert mod.main(['--storage', str(tmp_path)]) == 75
    assert calls[0][0].state['id'] == previous.state['id']
    assert calls[0][0].config.clip_count == 24
    assert previous.manifest.read_bytes() == snapshot
    assert len(list(previous.orders.glob('*/order.json'))) == 1
    summary = result(capsys)
    assert summary['mode'] == 'resumed' and summary['completed_clip_count'] == 7


def test_completed_order_starts_a_fresh_batch_on_the_next_request(tmp_path, monkeypatch, capsys):
    previous = saved_order(tmp_path, 'ready_for_review')
    calls = run_stub(monkeypatch)
    mod = importlib.import_module('clipping.autorun')
    assert mod.main(['--storage', str(tmp_path)]) == 75
    assert calls[0][0].state['id'] != previous.state['id']
    assert len(list(previous.orders.glob('*/order.json'))) == 2
    assert result(capsys)['mode'] == 'new'


def test_running_manual_order_is_observed_without_overwriting_its_state(tmp_path, capsys):
    previous = saved_order(tmp_path, 'running')
    snapshot = previous.manifest.read_bytes()
    mod = importlib.import_module('clipping.autorun')
    with order_lock(previous.folder):
        assert mod.main(['--storage', str(tmp_path)]) == 3
    summary = result(capsys)
    assert summary['status'] == 'already_running' and summary['id'] == previous.state['id']
    assert previous.manifest.read_bytes() == snapshot
    assert len(list(previous.orders.glob('*/order.json'))) == 1


def test_simultaneous_auto_requests_do_not_create_two_fresh_orders(tmp_path, monkeypatch, capsys):
    calls = run_stub(monkeypatch)
    folder = tmp_path / 'autorun'
    folder.mkdir()
    mod = importlib.import_module('clipping.autorun')
    with order_lock(folder):
        assert mod.main(['--storage', str(tmp_path)]) == 3
    assert calls == [] and not list(tmp_path.glob('orders/*/order.json'))
    assert result(capsys)['status'] == 'already_running'


def test_status_does_not_run_or_change_a_saved_order(tmp_path, monkeypatch, capsys):
    previous = saved_order(tmp_path, 'running')
    snapshot = previous.manifest.read_bytes()
    calls = run_stub(monkeypatch)
    mod = importlib.import_module('clipping.autorun')
    assert mod.main(['--storage', str(tmp_path), '--status']) == 0
    summary = result(capsys)
    assert summary['id'] == previous.state['id'] and summary['status'] == 'running'
    assert summary['mode'] == 'status' and calls == []
    assert previous.manifest.read_bytes() == snapshot


def test_status_with_no_order_does_not_create_one(tmp_path, capsys):
    mod = importlib.import_module('clipping.autorun')
    assert mod.main(['--storage', str(tmp_path), '--status']) == 0
    assert result(capsys)['status'] == 'not_started'
    assert not list(tmp_path.iterdir())


def test_explicit_changed_target_requires_a_new_order(tmp_path, monkeypatch, capsys):
    previous = saved_order(tmp_path)
    snapshot = previous.manifest.read_bytes()
    calls = run_stub(monkeypatch)
    mod = importlib.import_module('clipping.autorun')
    assert mod.main(['--storage', str(tmp_path), '--clips', '40']) == 2
    assert result(capsys)['reason'] == 'pending_order_settings_conflict'
    assert calls == [] and previous.manifest.read_bytes() == snapshot
    assert mod.main(['--storage', str(tmp_path), '--new', '--clips', '40']) == 75
    assert calls[0][0].config.clip_count == 40
    assert calls[0][0].state['id'] != previous.state['id']


def test_explicit_resume_uses_its_order_even_when_another_is_latest(tmp_path, monkeypatch, capsys):
    first = saved_order(tmp_path, count=24)
    saved_order(tmp_path, count=20)
    calls = run_stub(monkeypatch)
    mod = importlib.import_module('clipping.autorun')
    assert mod.main(['--storage', str(tmp_path), '--resume', first.state['id']]) == 75
    assert calls[0][0].state['id'] == first.state['id']
    assert result(capsys)['mode'] == 'resumed'


def test_corrupt_latest_pointer_is_redacted_and_does_not_start_over(tmp_path, monkeypatch, capsys):
    calls = run_stub(monkeypatch)
    orders = tmp_path / 'orders'
    orders.mkdir()
    atomic_json(orders / 'latest.json', {'id': 'SECRET_SENTINEL'})
    mod = importlib.import_module('clipping.autorun')
    assert mod.main(['--storage', str(tmp_path)]) == 2
    summary = result(capsys)
    assert summary['status'] == 'setup_required'
    assert 'SECRET_SENTINEL' not in json.dumps(summary) and calls == []


@pytest.mark.parametrize('count', ['0', '-1'])
def test_invalid_targets_do_not_create_an_order(tmp_path, count):
    mod = importlib.import_module('clipping.autorun')
    with pytest.raises(SystemExit) as error:
        mod.main(['--storage', str(tmp_path), '--clips', count])
    assert error.value.code == 2 and not list(tmp_path.iterdir())
