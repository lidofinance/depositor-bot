import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@pytest.fixture
def hung_host():
    """Accepts connections and never answers. Yields (url, accepted connection count)."""
    server = socket.create_server(('127.0.0.1', 0))
    accepted: list[socket.socket] = []

    def accept():
        while True:
            try:
                accepted.append(server.accept()[0])
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    yield f'http://127.0.0.1:{server.getsockname()[1]}', accepted
    server.close()
    for conn in accepted:
        conn.close()


@pytest.fixture
def healthy_host():
    """Answers GET with a CL-style body and POST as a JSON-RPC node returning '0x1'. Yields (url, request paths)."""
    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            hits.append(self.path)
            self._reply({'data': {}})

        def do_POST(self):
            hits.append(self.path)
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self._reply({'jsonrpc': '2.0', 'id': request['id'], 'result': '0x1'})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_address[1]}', hits
    server.shutdown()
    server.server_close()
