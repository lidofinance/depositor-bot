import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest
from eth_typing import URI
from web3 import Web3
from web3_multi_provider import FallbackProvider

import variables
from blockchain.web3_extentions.private_relay import PrivateRelayClient
from providers.fallback_provider import FallbackProviderModule, rpc_request_kwargs

pytestmark = pytest.mark.unit


class _RecordingRpcHandler(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        _RecordingRpcHandler.seen.append(dict(self.headers))
        body = json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': '0x1'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def rpc_url():
    _RecordingRpcHandler.seen = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), _RecordingRpcHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()


def test_user_agent_has_app_name_and_version():
    assert f'depositor-bot/{variables.BUILD_INFO["version"]}' == variables.USER_AGENT


@pytest.mark.parametrize(
    'make_provider',
    [
        pytest.param(lambda url: FallbackProviderModule([url]), id='el'),
        pytest.param(lambda url: FallbackProvider([url], request_kwargs=rpc_request_kwargs()), id='data-bus'),
    ],
)
def test_rpc_requests_carry_the_app_user_agent(rpc_url, make_provider):
    assert Web3(make_provider(rpc_url)).eth.chain_id == 1

    headers = _RecordingRpcHandler.seen[-1]
    assert headers['User-Agent'] == variables.USER_AGENT
    # Custom headers replace web3's defaults; the JSON content type must survive.
    assert headers['Content-Type'] == 'application/json'


def test_relay_requests_carry_the_app_user_agent():
    client = PrivateRelayClient(MagicMock(), URI('https://relay.example/rpc'), '0x' + 'aa' * 32)

    with patch('blockchain.web3_extentions.private_relay.requests.post') as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'result': '0x1'}
        client._handle_post_request('eth_test', [])

    assert post.call_args.kwargs['headers']['User-Agent'] == variables.USER_AGENT
