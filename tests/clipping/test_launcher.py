import importlib
import sys
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


def test_native_launcher_starts_local_clipping_app(monkeypatch):
    calls = []
    monkeypatch.setattr('uvicorn.run', lambda app, **options: calls.append((app, options)))
    monkeypatch.setattr(sys, 'argv', ['clipping', '--port', '8001'])
    importlib.import_module('clipping.__main__').main()
    assert calls == [('clipping.app:app', {'host': '127.0.0.1', 'port': 8001})]


def test_discovery_launcher_starts_a_new_worker_with_one_preview(monkeypatch, unused_tcp_port):
    calls = []
    monkeypatch.setenv('CLIPPING_AUTOMATION', '')
    monkeypatch.setattr('uvicorn.run', lambda app, **kwargs: calls.append((app, kwargs)))
    monkeypatch.setattr(sys, 'argv', ['clipping', '--discover', '--port', str(unused_tcp_port)])
    importlib.import_module('clipping.__main__').main()
    import os
    assert os.environ['CLIPPING_AUTOMATION'] == 'trends'
    assert calls[0][0] == 'clipping.app:app'


def test_discovery_launcher_does_not_reuse_an_old_network_worker(monkeypatch, capsys):
    import socket
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        monkeypatch.setattr(sys, 'argv', ['clipping', '--discover', '--port', str(occupied.getsockname()[1])])
        monkeypatch.setattr('uvicorn.run', lambda *args, **kwargs: pytest.fail('Reused the occupied port'))
        with pytest.raises(SystemExit) as failure:
            importlib.import_module('clipping.__main__').main()
        assert failure.value.code == 2
    assert 'Stop the existing workspace' in capsys.readouterr().out


def test_ishowspeed_launcher_starts_the_preset_without_a_form(monkeypatch, unused_tcp_port):
    monkeypatch.setenv('CLIPPING_AUTOMATION', '')
    monkeypatch.setattr('uvicorn.run', lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, 'argv', ['clipping', '--ishowspeed', '--port', str(unused_tcp_port)])
    importlib.import_module('clipping.__main__').main()
    import os
    assert os.environ['CLIPPING_AUTOMATION'] == 'ishowspeed'


def test_ishowspeed_launcher_reopens_an_existing_workspace_instead_of_binding_again(monkeypatch, capsys):
    class ExistingWorkspace(BaseHTTPRequestHandler):
        posts = 0

        def reply(self, value):
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            assert self.path == '/openapi.json'
            self.reply({'info': {'title': 'Clipping Workflow'}, 'paths': {
                '/api/v1/clipping/automations/ishowspeed/runs': {}}})

        def do_POST(self):
            assert self.path == '/api/v1/clipping/automations/ishowspeed/runs'
            assert json.loads(self.rfile.read(int(self.headers['Content-Length']))) == {}
            type(self).posts += 1
            self.reply({'id': 'saved-preview', 'status': 'queued'})

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), ExistingWorkspace)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        calls = []
        monkeypatch.setenv('CLIPPING_AUTOMATION', '')
        monkeypatch.setattr('uvicorn.run', lambda *args, **kwargs: calls.append(args))
        monkeypatch.setattr(sys, 'argv', ['clipping', '--ishowspeed', '--port', str(server.server_port)])
        importlib.import_module('clipping.__main__').main()
        assert calls == [], 'The running workspace must be reused'
        assert ExistingWorkspace.posts == 1
        assert 'saved-preview' in capsys.readouterr().out
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)
