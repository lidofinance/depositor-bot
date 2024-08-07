import logging
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler

import requests
import variables

logger = logging.getLogger(__name__)

_last_pulse = datetime.now()


def pulse():
    try:
        requests.get(f'http://localhost:{variables.HEALTHCHECK_SERVER_PORT}/pulse/', timeout=10)
    except requests.exceptions.ConnectionError as error:
        logger.warning({'msg': 'Healthcheck server is not responding.', 'error': str(error)})


class PulseRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        global _last_pulse

        if self.path == '/pulse/':
            _last_pulse = datetime.now()

        # timedelta should be higher than one epoch
        if datetime.now() - _last_pulse > timedelta(minutes=10):
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"metrics": "fail", "reason": "timeout exceeded"}\n')
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"metrics": "ok", "reason": "ok"}\n')

    def log_request(self, *args, **kwargs):
        # Disable non-error logs
        pass


def start_pulse_server():
    server = HTTPServer(
        ('localhost', variables.HEALTHCHECK_SERVER_PORT),
        RequestHandlerClass=PulseRequestHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
