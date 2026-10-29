import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

import pytest
from web3 import Web3
from web3_multi_provider import FallbackProvider

import variables
from main import check_providers_chain_ids, main

HOODI_CHAIN_ID = 560048


@pytest.mark.unit
@pytest.mark.parametrize(
    'address,endpoints',
    [
        (None, ['https://rpc.gnosis.example']),
        ('0x37De961D6bb5865867aDd416be07189D2Dd960e6', []),
    ],
)
def test_main_requires_databus_config(address, endpoints):
    with (
        patch.object(variables, 'ONCHAIN_TRANSPORT_ADDRESS', address),
        patch.object(variables, 'ONCHAIN_TRANSPORT_RPC_ENDPOINTS', endpoints),
        patch('main.start_pulse_server') as pulse,
        pytest.raises(ValueError, match='Data Bus is the only message transport'),
    ):
        main('pauser')
    pulse.assert_not_called()


class _JsonRpcHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/rate-limited':
            self.send_response(429)
            self.end_headers()
            return
        body = json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': hex(HOODI_CHAIN_ID)}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def rpc_url():
    server = ThreadingHTTPServer(('127.0.0.1', 0), _JsonRpcHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()


def _client(chain_id: int) -> Mock:
    client = Mock()
    client.check_providers_consistency.return_value = chain_id
    return client


@pytest.mark.unit
def test_check_providers_chain_ids__first_el_provider_rate_limited__falls_back(rpc_url):
    w3 = Web3(FallbackProvider([f'{rpc_url}/rate-limited', f'{rpc_url}/healthy']))

    check_providers_chain_ids(w3, _client(HOODI_CHAIN_ID), _client(HOODI_CHAIN_ID))


@pytest.mark.unit
def test_check_providers_chain_ids__layers_on_different_chains__raises(rpc_url):
    w3 = Web3(FallbackProvider([f'{rpc_url}/healthy']))

    with pytest.raises(ValueError, match='Different chain ids detected'):
        check_providers_chain_ids(w3, _client(1), _client(HOODI_CHAIN_ID))
