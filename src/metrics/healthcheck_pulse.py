import logging
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import variables

logger = logging.getLogger(__name__)

# Liveness fails when no cycle has pulsed for this long. Should be higher than one epoch.
PULSE_TIMEOUT = timedelta(minutes=10)
# Longest server error text written to the log. The text can quote client input.
MAX_LOGGED_ERROR_LENGTH = 256

_last_pulse = datetime.now()
_ready = threading.Event()


def pulse() -> None:
    """Record that the bot is alive. Called by the executor every cycle, in-process: the server has no route that
    refreshes liveness, so nothing outside the process can keep a stuck bot looking healthy."""
    global _last_pulse
    _last_pulse = datetime.now()


def mark_ready() -> None:
    """Switch /ready to 200 for the rest of the process lifetime. It never flips back: liveness covers a stuck bot."""
    if not _ready.is_set():
        logger.info({'msg': 'Bot is ready.'})
        _ready.set()


def is_alive() -> bool:
    return datetime.now() - _last_pulse <= PULSE_TIMEOUT


def is_ready() -> bool:
    return _ready.is_set()


class PulseRequestHandler(BaseHTTPRequestHandler):
    # Seconds to wait for a client to send its request. Without it a stalled client holds the connection forever.
    timeout = 5

    def do_GET(self):
        if self.path == '/healthcheck':
            self._respond(is_alive(), b'timeout exceeded')
        elif self.path == '/ready':
            self._respond(is_ready(), b'not ready')
        else:
            self.send_response(404)
            self.end_headers()

    def _respond(self, ok: bool, reason: bytes) -> None:
        if ok:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"metrics": "ok", "reason": "ok"}\n')
        else:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"metrics": "fail", "reason": "' + reason + b'"}\n')

    def log_request(self, *args, **kwargs):
        # Disable non-error logs
        pass

    def log_error(self, format, *args):
        # Route the server's own errors (for example a read timeout) through the JSON logger instead of stderr
        # Capped: send_error quotes the client's request line, up to 64 KiB of it.
        error = (format % args)[:MAX_LOGGED_ERROR_LENGTH]
        logger.warning({'msg': 'Healthcheck server error.', 'client': self.client_address[0], 'error': error})


def start_pulse_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    """Serve /healthcheck (liveness) and /ready (readiness) on host:port in a daemon thread.

    Defaults to HEALTHCHECK_SERVER_HOST and HEALTHCHECK_SERVER_PORT.
    """
    server = ThreadingHTTPServer(
        (variables.HEALTHCHECK_SERVER_HOST if host is None else host, variables.HEALTHCHECK_SERVER_PORT if port is None else port),
        RequestHandlerClass=PulseRequestHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
