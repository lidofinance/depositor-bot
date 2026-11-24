import pytest

from metrics import healthcheck_pulse
from metrics.healthcheck_probe import main, probe_url
from metrics.healthcheck_pulse import start_pulse_server

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    'host,expected',
    [
        ('0.0.0.0', 'http://127.0.0.1:9010/healthcheck'),
        ('::', 'http://127.0.0.1:9010/healthcheck'),
        ('', 'http://127.0.0.1:9010/healthcheck'),
        # A specific address does not accept loopback connections: call it as it is.
        ('10.0.0.7', 'http://10.0.0.7:9010/healthcheck'),
        ('fd00::7', 'http://[fd00::7]:9010/healthcheck'),
    ],
)
def test_probe_url(host, expected):
    assert probe_url(host, '9010') == expected


def test_probe_reaches_server_on_a_specific_host(monkeypatch):
    server = start_pulse_server('127.0.0.1', 0)
    try:
        healthcheck_pulse.pulse()
        monkeypatch.setenv('HEALTHCHECK_SERVER_HOST', '127.0.0.1')
        monkeypatch.setenv('HEALTHCHECK_SERVER_PORT', str(server.server_address[1]))

        assert main() == 0
    finally:
        server.shutdown()
        server.server_close()


def test_probe_fails_when_nothing_listens(monkeypatch):
    monkeypatch.setenv('HEALTHCHECK_SERVER_HOST', '127.0.0.1')
    monkeypatch.setenv('HEALTHCHECK_SERVER_PORT', '1')

    assert main() == 1
