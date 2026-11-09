import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from metrics.logging import REDACTED, JsonFormatter, key_secrets, url_secrets

REPO_ROOT = Path(__file__).resolve().parents[2]

EL_KEY = 'ELSENTINELKEY0001'
BUS_KEY = 'BUSSENTINELKEY002'
CL_KEY = 'CLSENTINELKEY0003'

# Connection refused on a local port produces the same urllib3 message a dead RPC does — offline.
LEAK_SCRIPT = """
import requests

from metrics.logging import logging

logger = logging.getLogger('leak')
try:
    requests.get('http://127.0.0.1:1/v2/ELSENTINELKEY0001', timeout=1)
except Exception as e:
    logger.error({'msg': 'Failed to fetch logs', 'err': repr(e)})
logger.info({'msg': 'endpoints', 'value': 'https://gnosis.example/rpc?dkey=BUSSENTINELKEY002'})
raise RuntimeError('CL down: https://cl.example/eth-beacon-chain/CLSENTINELKEY0003')
"""


def _record(msg) -> logging.LogRecord:
    return logging.LogRecord('test', logging.ERROR, __file__, 1, msg, None, None)


@pytest.mark.unit
def test_url_secrets_include_path_and_query():
    assert url_secrets('https://lb.drpc.org/ogrpc?network=ethereum&dkey=KEY12345') == {
        'https://lb.drpc.org/ogrpc?network=ethereum&dkey=KEY12345',
        '/ogrpc?network=ethereum&dkey=KEY12345',
    }


@pytest.mark.unit
def test_url_secrets_include_password_and_skip_short_paths():
    assert url_secrets('http://user:longpassword@node.example:8545/') == {
        'http://user:longpassword@node.example:8545/',
        'longpassword',
    }


@pytest.mark.unit
def test_key_secrets_cover_both_hex_forms():
    assert key_secrets('0xabcdef') == {'0xabcdef', 'abcdef'}
    assert key_secrets(None) == set()


@pytest.mark.unit
def test_formatter_redacts_every_field_and_keeps_json_valid():
    url = 'https://eth-mainnet.g.alchemy.com/v2/SECRETKEY123'
    formatter = JsonFormatter(url_secrets(url))

    line = formatter.format(_record({'msg': f'down {url}', 'err': "MaxRetryError('url: /v2/SECRETKEY123')"}))

    assert 'SECRETKEY123' not in line
    assert json.loads(line)['msg'] == f'down {REDACTED}'


@pytest.mark.unit
def test_formatter_redacts_plain_string_messages():
    formatter = JsonFormatter(['SECRETKEY123'])

    assert 'SECRETKEY123' not in formatter.format(_record('key SECRETKEY123'))


@pytest.mark.unit
def test_configured_endpoint_keys_never_reach_process_output():
    result = subprocess.run(
        [sys.executable, '-c', LEAK_SCRIPT],
        cwd=REPO_ROOT,
        env={
            'PATH': '/usr/bin:/bin',
            'PYTHONPATH': str(REPO_ROOT / 'src'),
            'WEB3_RPC_ENDPOINTS': f'http://127.0.0.1:1/v2/{EL_KEY}',
            'ONCHAIN_TRANSPORT_RPC_ENDPOINTS': f'https://gnosis.example/rpc?dkey={BUS_KEY}',
            'CL_API_URLS': f'https://cl.example/eth-beacon-chain/{CL_KEY}',
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert 'Failed to fetch logs' in output
    assert 'Uncaught exception. Shut down.' in output
    for key in (EL_KEY, BUS_KEY, CL_KEY):
        assert key not in output
