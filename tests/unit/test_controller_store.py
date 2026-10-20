import pytest


def test_resume_uses_database_after_manifest_export_failure(tmp_path, monkeypatch):
    from clipping import orchestrator
    controller = orchestrator.Controller(tmp_path, orchestrator.Config(), emit=lambda _: None)
    identifier = controller.state['id']
    old_export = orchestrator.atomic_json
    monkeypatch.setattr(orchestrator, 'atomic_json', lambda *args: (_ for _ in ()).throw(OSError('disk export failed')))
    with pytest.raises(OSError):
        controller.update(status='running', stage='transcription')
    monkeypatch.setattr(orchestrator, 'atomic_json', old_export)
    controller.manifest.write_text('{broken')
    (controller.orders / 'latest.json').unlink()
    resumed = orchestrator.Controller(tmp_path, resume='latest', emit=lambda _: None)
    assert resumed.state['id'] == identifier
    assert resumed.state['stage'] == 'transcription'


def test_clip_repository_preserves_links_and_enforces_foreign_keys(tmp_path):
    from app.repositories.store import Store
    from clipping.orchestrator import Config, Controller
    controller = Controller(tmp_path, Config(), emit=lambda _: None)
    store = Store(tmp_path / 'content-reward.db')
    store.save_clip({'id': 'clip-one', 'order_id': controller.state['id'],
                     'path': 'clip.mp4', 'sha256': 'f' * 64})
    assert store.get_clip('clip-one')['order_id'] == controller.state['id']
    assert len(store.list_clips()) == 1


def test_two_controllers_cannot_overwrite_a_concurrent_update(tmp_path):
    from clipping.orchestrator import Config, Controller
    first = Controller(tmp_path, Config(), emit=lambda _: None)
    second = Controller(tmp_path, resume=first.state['id'], emit=lambda _: None)
    first.update(status='running', stage='transcription')
    with pytest.raises(ValueError, match='changed'):
        second.update(status='running', stage='stale_reader')
    state, revision = first.store.read_order(first.state['id'])
    assert state['stage'] == 'transcription' and revision == first._revision
