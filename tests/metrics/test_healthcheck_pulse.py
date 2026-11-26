import socket
from datetime import datetime, timedelta

import pytest
import requests

import variables
from metrics import healthcheck_pulse as healthcheck
from metrics.healthcheck_pulse import start_pulse_server

pytestmark = pytest.mark.unit


@pytest.fixture
def server():
    server = start_pulse_server('127.0.0.1', 0)
    yield server
    server.shutdown()
    server.server_close()


def url(server, path):
    host, port = server.server_address[:2]
    return f'http://{host}:{port}{path}'


def test_pulse_server_binds_to_the_given_host(server, monkeypatch):
    monkeypatch.setattr(healthcheck, '_last_pulse', datetime.now())

    response = requests.get(url(server, '/healthcheck'), timeout=5)

    assert server.server_address[0] == '127.0.0.1'
    assert response.status_code == 200
    assert response.json() == {'metrics': 'ok', 'reason': 'ok'}


def test_healthcheck_fails_without_pulse_for_ten_minutes(server, monkeypatch):
    monkeypatch.setattr(healthcheck, '_last_pulse', datetime.now() - timedelta(minutes=11))

    response = requests.get(url(server, '/healthcheck'), timeout=5)

    assert response.status_code == 503
    assert response.json()['metrics'] == 'fail'


def test_in_process_pulse_refreshes_the_healthcheck(server, monkeypatch):
    monkeypatch.setattr(healthcheck, '_last_pulse', datetime.now() - timedelta(minutes=11))

    healthcheck.pulse()
    response = requests.get(url(server, '/healthcheck'), timeout=5)

    assert response.status_code == 200


def test_http_request_cannot_fake_a_pulse(server, monkeypatch):
    # The server listens on all interfaces: a request from another pod must not keep a stuck bot alive.
    monkeypatch.setattr(healthcheck, '_last_pulse', datetime.now() - timedelta(minutes=11))

    assert requests.get(url(server, '/pulse/'), timeout=5).status_code == 404
    assert requests.get(url(server, '/healthcheck'), timeout=5).status_code == 503


@pytest.fixture
def not_ready(monkeypatch):
    monkeypatch.setattr(healthcheck, '_ready', healthcheck.threading.Event())


def test_ready_is_503_until_marked_and_never_flips_back(server, not_ready, monkeypatch):
    assert requests.get(url(server, '/ready'), timeout=5).status_code == 503

    healthcheck.mark_ready()
    # A stale pulse fails liveness, not readiness.
    monkeypatch.setattr(healthcheck, '_last_pulse', datetime.now() - timedelta(minutes=11))

    response = requests.get(url(server, '/ready'), timeout=5)
    assert response.status_code == 200
    assert response.json() == {'metrics': 'ok', 'reason': 'ok'}


def test_unknown_path_is_404(server):
    assert requests.get(url(server, '/'), timeout=5).status_code == 404


def test_stalled_client_does_not_block_other_requests(server, monkeypatch):
    monkeypatch.setattr(healthcheck, '_last_pulse', datetime.now())
    stalled = socket.create_connection(server.server_address[:2], timeout=5)

    try:
        response = requests.get(url(server, '/healthcheck'), timeout=2)
    finally:
        stalled.close()

    assert response.status_code == 200


def test_stalled_client_is_disconnected_after_timeout(server, monkeypatch, caplog):
    monkeypatch.setattr(healthcheck.PulseRequestHandler, 'timeout', 0.2)
    stalled = socket.create_connection(server.server_address[:2], timeout=5)

    try:
        with caplog.at_level('WARNING', logger='metrics.healthcheck_pulse'):
            assert stalled.recv(1) == b''
    finally:
        stalled.close()

    [record] = caplog.records
    assert record.msg['msg'] == 'Healthcheck server error.'
    assert 'timed out' in record.msg['error']


def test_invalid_request_line_is_logged_truncated(server, caplog):
    client = socket.create_connection(server.server_address[:2], timeout=5)

    try:
        with caplog.at_level('WARNING', logger='metrics.healthcheck_pulse'):
            client.sendall(b'X' * 60_000 + b'\r\n\r\n')
            # The error page comes after the log line: once it arrives, the record is there.
            assert client.recv(1024)
    finally:
        client.close()

    [record] = caplog.records
    assert record.msg['msg'] == 'Healthcheck server error.'
    assert len(record.msg['error']) == healthcheck.MAX_LOGGED_ERROR_LENGTH


def test_server_does_not_serve_files(server, monkeypatch):
    monkeypatch.setattr(healthcheck, '_last_pulse', datetime.now())

    response = requests.head(url(server, '/main.py'), timeout=5)

    assert response.status_code == 501


def test_default_bind_is_all_interfaces():
    # Kubernetes probes hit the pod IP, so a server on localhost only would never answer them.
    assert variables.HEALTHCHECK_SERVER_HOST == '0.0.0.0'


def test_server_uses_configured_host_and_port(monkeypatch):
    monkeypatch.setattr(variables, 'HEALTHCHECK_SERVER_HOST', '127.0.0.1')
    monkeypatch.setattr(variables, 'HEALTHCHECK_SERVER_PORT', 0)

    server = start_pulse_server()
    try:
        assert server.server_address[0] == '127.0.0.1'
    finally:
        server.shutdown()
        server.server_close()
