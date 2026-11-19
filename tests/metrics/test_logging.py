import importlib
import json
import logging
import sys

import pytest
from logmask import JsonFormatter, SafeStreamHandler

import variables

pytestmark = pytest.mark.unit

RPC = 'https://rpc.example/v3/secret-key-1'
CL = 'https://user:cl-password@beacon.example/'
KEY = '0x' + 'ab' * 32


@pytest.fixture
def root_logger(monkeypatch):
    """The logging of the bot configured from an environment with secrets, as at startup."""
    monkeypatch.setenv('WEB3_RPC_ENDPOINTS', RPC)
    monkeypatch.setenv('CL_API_URLS', CL)
    monkeypatch.setenv('WALLET_PRIVATE_KEY', KEY)
    importlib.reload(variables)
    import metrics.logging

    importlib.reload(metrics.logging)
    yield logging.getLogger()
    monkeypatch.undo()
    importlib.reload(variables)


def _bot_handler(root: logging.Logger) -> SafeStreamHandler:
    # pytest adds its own capture handlers to the root logger around every test; the bot's handler is the only stream one.
    (handler,) = (h for h in root.handlers if isinstance(h, SafeStreamHandler))
    return handler


def test_log_lines_are_json_with_private_values_masked(root_logger):
    handler = _bot_handler(root_logger)
    assert isinstance(handler.formatter, JsonFormatter)

    message = {'msg': 'RPC failed', 'url': RPC, 'path': '/v3/secret-key-1', 'cl': CL, 'key': KEY}
    line = handler.format(logging.LogRecord('test', logging.ERROR, __file__, 1, message, None, None))

    assert 'secret-key' not in line
    assert 'cl-password' not in line
    assert KEY not in line
    assert json.loads(line)['msg'] == 'RPC failed'


def test_logs_go_to_stdout(root_logger):
    assert _bot_handler(root_logger).stream is sys.stdout


def test_unhandled_exceptions_go_through_the_logger(root_logger):
    assert sys.excepthook is not sys.__excepthook__


@pytest.mark.parametrize('name', ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'debug', 'warning'])
def test_every_documented_log_level_works(monkeypatch, name):
    monkeypatch.setenv('LOG_LEVEL', name)
    importlib.reload(variables)
    import metrics.logging

    try:
        importlib.reload(metrics.logging)
        assert logging.getLogger().level == logging.getLevelName(name.upper())
    finally:
        monkeypatch.undo()
        importlib.reload(variables)
        importlib.reload(metrics.logging)


def test_dict_message_keeps_bytes_as_hex(root_logger):
    record = logging.LogRecord('test', logging.INFO, __file__, 1, {'msg': 'root', 'value': b'\x0a\x0b'}, None, None)

    assert json.loads(_bot_handler(root_logger).format(record))['value'] == '0x0a0b'
