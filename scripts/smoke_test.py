"""Offline environment probes; never discover, download or publish content."""

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def api_probe(folder):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, CLIPPING_DATABASE=str(folder / 'api.db'),
               CLIPPING_STORAGE=str(folder / 'api-storage'), CLIPPING_TREND_AGENT='false',
               CLIPPING_AUTOMATION='')
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'clipping.app:app',
        '--host', '127.0.0.1', '--port', str(port), '--log-level', 'error'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with opener.open(f'http://127.0.0.1:{port}/health', timeout=.5) as response:
                    return response.status == 200 and json.load(response)['status'] == 'healthy'
            except (OSError, ValueError):
                time.sleep(.1)
        return False
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def check_environment(*, storage=None, check_api=True):
    from app.core.config import load_settings
    from clipping.orchestrator import ffmpeg_supports_bounded_sections
    from clipping.workflow import ClippingWorkflow

    checks = {}

    def record(name, passed, detail):
        checks[name] = dict(passed=bool(passed), detail=detail)

    try:
        settings = load_settings()
        record('configuration', True, 'Validated non-secret settings; publishing disabled')
    except Exception:
        return {'passed': False, 'checks': {'configuration': {'passed': False, 'detail': 'Invalid configuration'}}}
    for name in ('ffmpeg', 'ffprobe'):
        binary = shutil.which(name)
        okay = False
        if binary:
            try:
                response = subprocess.run([binary, '-version'], capture_output=True, timeout=5,
                                          text=True, encoding='utf-8', errors='replace')
                okay = response.returncode == 0 and (
                    name != 'ffmpeg' or ffmpeg_supports_bounded_sections(response.stdout))
            except (OSError, subprocess.TimeoutExpired):
                pass
        detail = ('FFmpeg 9.0+ or an autobuild from 2026-08-05 is required for bounded sections'
                  if name == 'ffmpeg' else 'Executable version probe')
        record(name, okay, detail)
    modules = ('fastapi', 'uvicorn', 'multipart', 'pydantic', 'yaml', 'yt_dlp')
    record('dependencies', all(importlib.util.find_spec(name) for name in modules), 'Core import availability')
    record('whisper', importlib.util.find_spec('faster_whisper') is not None,
           'Install .[transcription] in this interpreter; model readiness is reported by /health')
    root = Path(storage or settings.paths.storage).resolve()
    try:
        (root / 'temp').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='smoke-', dir=root / 'temp') as temporary:
            folder = Path(temporary).resolve()
            if not folder.is_relative_to(root):
                raise ValueError('Invalid smoke directory')
            marker = folder / 'writable'
            marker.write_text('smoke')
            record('storage', marker.read_text() == 'smoke', 'Temporary write/read probe')
            engine = ClippingWorkflow(folder / 'workflow.db', folder / 'media')
            with engine.connection() as database:
                record('database', database.execute('PRAGMA integrity_check').fetchone()[0] == 'ok',
                       'Isolated SQLite initialization and integrity check')
            result = []
            worker = threading.Thread(target=lambda: result.append(engine.consume_once()), daemon=True)
            worker.start()
            worker.join(5)
            record('worker', not worker.is_alive() and result == [False], 'Empty queue consumed without side effects')
            if check_api:
                record('api', api_probe(folder), 'Loopback HTTP startup and /health; research disabled')
    except Exception:
        record('runtime', False, 'Runtime storage/database/API probe failed; no provider details emitted')
    return {'passed': all(check['passed'] for check in checks.values()), 'checks': checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', type=Path)
    parser.add_argument('--skip-api', action='store_true')
    options = parser.parse_args(argv)
    report = check_environment(storage=options.storage, check_api=not options.skip_api)
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
