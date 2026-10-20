"""Start the clipping workspace and its built-in worker without n8n."""

import argparse
import http.client
import json
import os
import socket


def reuse_workspace(host, port):
    if host not in ('127.0.0.1', 'localhost', '0.0.0.0'):
        return False
    endpoint = '/api/v1/clipping/automations/ishowspeed/runs'
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        try:
            connection.request('GET', '/openapi.json')
            response = connection.getresponse()
            if response.status != 200:
                return False
            schema = json.loads(response.read(1024 * 1024))
            if (not isinstance(schema, dict) or not isinstance(schema.get('info'), dict)
                    or not isinstance(schema.get('paths'), dict)
                    or schema['info'].get('title') != 'Clipping Workflow'
                    or endpoint not in schema.get('paths', {})):
                return False
        except (OSError, ValueError, http.client.HTTPException):
            return False
        connection.close()
        connection.request('POST', endpoint, body='{}', headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        result = json.loads(response.read(1024 * 1024))
        if response.status not in (200, 202) or not isinstance(result, dict) or not result.get('id'):
            detail = result.get('detail') if isinstance(result, dict) else None
            raise RuntimeError(detail or 'The running workspace could not start the automatic preview')
        print(f"Automatic preview {result['id']}: {result.get('status', 'saved')}")
        print(f'Workspace: http://127.0.0.1:{port}/')
        return True
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description='Run the clipping workspace and built-in workflow worker.')
    parser.add_argument('--host', default='127.0.0.1', help='Bind address (default: local machine only)')
    parser.add_argument('--port', type=int, default=8000, help='HTTP port (default: 8000)')
    parser.add_argument('--ishowspeed', action='store_true',
                        help='Start the automatic IShowSpeed preview without form selections')
    parser.add_argument('--discover', action='store_true',
                        help='Search recent long YouTube videos and prepare one real captioned highlight')
    options = parser.parse_args()
    if options.discover and options.ishowspeed:
        parser.error('Choose either long-video discovery or the saved IShowSpeed preset')
    if options.discover:
        # Reusing a server also reuses its network environment. Start a fresh worker
        # so a normal-terminal launch actually performs discovery in that terminal.
        with socket.socket() as listener:
            try:
                listener.bind((options.host, options.port))
            except OSError:
                print(f'Port {options.port} is occupied. Stop the existing workspace with Ctrl+C, '
                      'then run this command again, or choose --port with a free port.')
                raise SystemExit(2)
        os.environ['CLIPPING_AUTOMATION'] = 'trends'
        os.environ['CLIPPING_TREND_AGENT'] = 'true'
        print('Search long YouTube videos -> select one highlight -> transcribe speech -> burn subtitles.')
        print(f'Workspace: http://127.0.0.1:{options.port}/')
    if options.ishowspeed:
        os.environ['CLIPPING_AUTOMATION'] = 'ishowspeed'
        if reuse_workspace(options.host, options.port):
            return

    import uvicorn

    uvicorn.run('clipping.app:app', host=options.host, port=options.port)


if __name__ == '__main__':
    main()
