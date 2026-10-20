import importlib
import importlib.util
import json
import os
import sys
import time

import pytest

from clipping import media


def descendant_command(tmp_path, *, finish=False):
    started, orphan = tmp_path / 'started', tmp_path / 'orphan'
    child = f'from pathlib import Path; import time; time.sleep(2); Path({str(orphan)!r}).write_text("alive")'
    parent = (f'import subprocess,sys,time; from pathlib import Path; '
              f'subprocess.Popen([sys.executable,"-c",{child!r}], stdin=subprocess.DEVNULL, '
              f'stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); '
              f'Path({str(started)!r}).write_text("started"); ' +
              ('print("finished")' if finish else 'time.sleep(10)'))
    return [sys.executable, '-c', parent], started, orphan


def test_pause_stops_source_descendants(tmp_path):
    args, started, orphan = descendant_command(tmp_path)
    with pytest.raises(media.ProcessingInterrupted):
        media.command(args, should_stop=started.exists, timeout=10)
    assert started.exists()
    time.sleep(2.2)
    assert not orphan.exists(), 'A paused downloader left a child running'


@pytest.mark.skipif(os.name != 'nt', reason='Windows job ownership')
def test_finished_source_does_not_leave_detached_child(tmp_path):
    args, started, orphan = descendant_command(tmp_path, finish=True)
    assert media.command(args, kill_tree=True, timeout=10).strip() == 'finished'
    assert started.exists()
    time.sleep(2.2)
    assert not orphan.exists(), 'A completed source left its child running'


@pytest.mark.skipif(os.name != 'nt', reason='Windows job ownership')
def test_failed_job_assignment_never_starts_media_target(tmp_path, monkeypatch):
    assert importlib.util.find_spec('clipping.windows_process'), 'Owned Windows media process support is missing'
    module = importlib.import_module('clipping.windows_process')
    marker = tmp_path / 'must-not-run'

    def refused(*args):
        raise PermissionError('Assignment refused')

    monkeypatch.setattr(module.WindowsJob, 'assign', refused)
    target = f'from pathlib import Path; Path({str(marker)!r}).write_text("ran")'
    with pytest.raises(ValueError, match='manage|process'):
        media.command([sys.executable, '-c', target], kill_tree=True, timeout=5)
    assert not marker.exists()


def test_controlled_command_preserves_arguments_output_and_working_directory(tmp_path):
    target = 'import json,os,sys; print(json.dumps([os.getcwd(),*sys.argv[1:]]))'
    result = media.command([sys.executable, '-c', target, 'argument with spaces', 'é'],
                           cwd=tmp_path, kill_tree=True, timeout=5)
    assert json.loads(result) == [str(tmp_path), 'argument with spaces', 'é']


def test_controlled_command_preserves_failure_feedback():
    with pytest.raises(ValueError, match='fixture failure'):
        media.command([sys.executable, '-c', 'import sys; sys.stderr.write("fixture failure"); sys.exit(7)'],
                      kill_tree=True, timeout=5)


def test_missing_controlled_executable_reports_installation():
    with pytest.raises(ValueError, match='Install'):
        media.command(['clipping-test-missing-executable'], kill_tree=True, timeout=5)
