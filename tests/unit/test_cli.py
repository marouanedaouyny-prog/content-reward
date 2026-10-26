import json
import os

import pytest


def test_cli_status_does_not_create_a_new_order(tmp_path, capsys):
    from clipping.cli import main
    assert main(['status', '--storage', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'not_started'
    assert not list(tmp_path.iterdir())


def test_cli_library_reports_niches_without_starting_a_run(tmp_path, capsys):
    from clipping.cli import main
    assert main(['library', '--storage', str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['publishing_enabled'] is False
    assert {'sports', 'streams', 'business', 'education'} <= {item['id'] for item in report['categories']}
    assert all(item['clip_count'] == 0 for item in report['categories'])
    assert not list(tmp_path.glob('orders/*/order.json'))


def test_cli_recovery_preserves_audit_default_and_reports_partial_work(tmp_path, monkeypatch, capsys):
    from clipping.cli import main
    calls = []

    def recover(storage, order, *, restore, organize=False):
        calls.append((storage, order, restore, organize))
        return {'blocked_count': 1, 'restored_count': int(restore), 'status': 'partial'}

    monkeypatch.setattr('clipping.recovery.recover_order', recover)
    assert main(['recover', 'saved-order', '--storage', str(tmp_path)]) == 2
    assert main(['recover', 'saved-order', '--restore', '--storage', str(tmp_path)]) == 2
    assert main(['recover', 'saved-order', '--restore', '--organize', '--storage', str(tmp_path)]) == 2
    assert calls == [(tmp_path, 'saved-order', False, False), (tmp_path, 'saved-order', True, False),
                     (tmp_path, 'saved-order', True, True)]
    capsys.readouterr()


def test_cli_recovery_busy_order_does_not_start_a_duplicate(tmp_path, monkeypatch, capsys):
    from clipping.cli import main
    from clipping.orchestrator import OrderBusy

    def busy(*args, **kwargs):
        raise OrderBusy()

    monkeypatch.setattr('clipping.recovery.recover_order', busy)
    assert main(['recover', 'saved-order', '--restore', '--storage', str(tmp_path)]) == 3
    assert json.loads(capsys.readouterr().out)['status'] == 'already_running'


def test_cli_revision_passes_only_explicit_local_corrections(tmp_path, monkeypatch, capsys):
    from clipping.cli import main
    calls = []
    path = tmp_path / 'corrections.json'
    niche = tmp_path / 'niche.json'
    niche.write_text('{"niche":"ai-technology","rationale":"Editor review."}')
    def revise(storage, clip_id, transcript_path, **options):
        calls.append((storage, clip_id, transcript_path, options))
        return {'status': 'revised'}
    monkeypatch.setattr('clipping.revisions.revise_clip', revise)
    assert main(['revise', 'parent', '--storage', str(tmp_path), '--transcript', str(path),
                 '--post-caption', 'Correct separate caption.', '--niche-review', str(niche)]) == 0
    assert calls == [(tmp_path, 'parent', path, {'post_caption': 'Correct separate caption.',
        'niche_review': {'niche': 'ai-technology', 'rationale': 'Editor review.'}})]
    assert json.loads(capsys.readouterr().out)['status'] == 'revised'


def test_cli_run_forwards_bounded_production_arguments(tmp_path, monkeypatch):
    from clipping.cli import main
    calls = []
    monkeypatch.setattr('clipping.autorun.main', lambda args: calls.append(args) or 0)
    assert main(['run', '--target', '24', '--storage', str(tmp_path)]) == 0
    assert calls[0][calls[0].index('--clips') + 1] == '24'
    assert '--storage' in calls[0]


def test_cli_run_forwards_explicit_learning_context_file(tmp_path, monkeypatch):
    from clipping.cli import main
    calls = []
    monkeypatch.setattr('clipping.autorun.main', lambda args: calls.append(args) or 0)
    path = tmp_path / 'learning.json'
    assert main(['run', '--learning-context', str(path)]) == 0
    assert calls[0][calls[0].index('--learning-context') + 1] == str(path)


def test_cli_api_uses_requested_runtime_storage_and_preserves_independent_job_database(tmp_path, monkeypatch):
    import asyncio
    from pathlib import Path
    from clipping.cli import main
    from clipping.app import app
    requested = tmp_path / 'requested-workspace'
    previous = tmp_path / 'previous-workspace'
    database = tmp_path / 'independent-jobs.db'
    monkeypatch.setenv('CLIPPING_STORAGE', str(previous))
    monkeypatch.setenv('CLIPPING_DATABASE', str(database))
    monkeypatch.setenv('CLIPPING_TREND_AGENT', 'false')
    monkeypatch.delenv('CLIPPING_AUTOMATION', raising=False)
    launches = []

    def serve(application, **options):
        launches.append((application, options))

        async def inspect_runtime():
            async with app.router.lifespan_context(app):
                assert app.state.workflow.storage == requested.resolve()
                assert app.state.domain_store.path == requested.resolve() / 'content-reward.db'
                assert app.state.workflow.database == database.resolve()
                active_storage = Path(os.environ['CLIPPING_STORAGE'])
                assert active_storage == requested

        asyncio.run(inspect_runtime())

    monkeypatch.setattr('uvicorn.run', serve)
    assert main(['api', '--storage', str(requested), '--host', '127.0.0.1', '--port', '8123']) == 0
    assert launches == [('clipping.app:app', {'host': '127.0.0.1', 'port': 8123})]
    assert (requested / 'content-reward.db').is_file() and database.is_file()
    assert not previous.exists()
    restored_storage = os.environ['CLIPPING_STORAGE']
    unchanged_database = os.environ['CLIPPING_DATABASE']
    assert restored_storage == str(previous)
    assert unchanged_database == str(database)


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('fails', [False, True])
def test_cli_api_restores_storage_environment_after_server_exit(tmp_path, monkeypatch, existing, fails):
    from clipping.cli import main
    previous = str(tmp_path / 'previous-workspace') if existing else None
    requested = str(tmp_path / 'requested-workspace')
    if existing:
        monkeypatch.setenv('CLIPPING_STORAGE', previous)
    else:
        monkeypatch.delenv('CLIPPING_STORAGE', raising=False)

    def server(args):
        active_storage = os.environ.get('CLIPPING_STORAGE')
        assert active_storage == requested
        if fails:
            raise RuntimeError('simulated server failure')
        return 17

    monkeypatch.setattr('clipping.__main__.main', server)
    if fails:
        with pytest.raises(RuntimeError, match='simulated server failure'):
            main(['api', '--storage', requested])
    else:
        assert main(['api', '--storage', requested]) == 17
    restored_storage = os.environ.get('CLIPPING_STORAGE')
    assert restored_storage == previous


def test_legacy_module_launcher_dispatches_canonical_commands(monkeypatch):
    from clipping import __main__
    monkeypatch.setattr('clipping.cli.main', lambda args: 17 if args == ['status'] else 2)
    assert __main__.main(['status']) == 17


def test_legacy_module_launcher_dispatches_global_storage_before_command(monkeypatch):
    from clipping import __main__
    calls = []
    monkeypatch.setattr('clipping.cli.main', lambda args: calls.append(args) or 0)
    assert __main__.main(['--storage', 'isolated', 'status']) == 0
    assert calls == [['--storage', 'isolated', 'status']]
