import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_typing import URI, HexStr
from prometheus_client import REGISTRY
from web3 import Web3

from blockchain.web3_extentions.private_relay import PrivateRelayClient
from variables import PROMETHEUS_PREFIX

SIGNER_PRIVATE_KEY = '0x' + 'aa' * 32


@pytest.mark.unit
def test_flashbots_signature_format():
    """
    The relay (adapters/flashbots/signature.go) computes:
        hashedBody  = crypto.Keccak256Hash(body).Hex()     # "0xabcd..." WITH 0x prefix
        messageHash = accounts.TextHash([]byte(hashedBody)) # signs the 66-char string

    Go's Hash.Hex() includes the 0x prefix. Python's HexBytes.hex() does NOT.
    Both the hash and the signature must be 0x-prefixed in the header.
    """
    signer = Account.from_key(SIGNER_PRIVATE_KEY)
    method = 'eth_sendPrivateTransaction'
    params = [{'tx': '0xdeadbeef'}]

    body = {'jsonrpc': '2.0', 'id': '1', 'method': method, 'params': params}
    body_str = json.dumps(body)

    # Correct: hash WITH 0x prefix (matches Go's Hash.Hex()), signature WITH 0x
    body_hash_with_0x = Web3.to_hex(hexstr=HexStr(Web3.keccak(text=body_str).hex()))
    correct_message = encode_defunct(text=body_hash_with_0x)
    correct_sig = Web3.to_hex(hexstr=HexStr(signer.sign_message(correct_message).signature.hex()))

    # Wrong: hash WITHOUT 0x prefix (what HexBytes.hex() returns by default)
    wrong_message = encode_defunct(text=Web3.keccak(text=body_str).hex())
    wrong_sig = signer.sign_message(wrong_message).signature.hex()

    assert correct_sig != wrong_sig, 'Signatures must differ — confirms 0x prefix changes the message'

    headers, _ = PrivateRelayClient._get_rpc_request(method, params, signer)

    signing_address, relay_sig = headers['X-Flashbots-Signature'].split(':')
    assert signing_address == signer.address
    assert relay_sig == correct_sig
    assert relay_sig != wrong_sig


@pytest.mark.unit
def test_private_tx_is_0x_prefixed_raw_transaction():
    w3 = MagicMock()
    w3.eth.get_block.return_value = {'number': 100}
    sender = Account.from_key('0x' + 'bb' * 32)
    signed = sender.sign_transaction(
        {
            'chainId': 1,
            'nonce': 0,
            'to': sender.address,
            'value': 0,
            'gas': 21000,
            'maxFeePerGas': 10**9,
            'maxPriorityFeePerGas': 10**8,
            'type': 2,
        }
    )

    params = PrivateRelayClient(w3, 'http://relay', SIGNER_PRIVATE_KEY)._build_mev_send_bundle_params(signed, 5)

    assert params[0]['tx'].startswith('0x')
    assert bytes.fromhex(params[0]['tx'][2:]) == bytes(signed.raw_transaction)
    assert params[0]['maxBlockNumber'] == hex(105)


def _relay_samples(method: str, code: str) -> float:
    return (
        REGISTRY.get_sample_value(
            f'{PROMETHEUS_PREFIX}_private_relay_requests_duration_seconds_count',
            {'method': method, 'code': code, 'domain': 'relay.example'},
        )
        or 0
    )


@pytest.mark.unit
def test_relay_request_is_measured():
    client = PrivateRelayClient(MagicMock(), URI('https://relay.example/rpc'), SIGNER_PRIVATE_KEY)
    before = _relay_samples('eth_test', '200')

    with patch('blockchain.web3_extentions.private_relay.requests.post') as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'result': '0x1'}
        assert client._handle_post_request('eth_test', []) == {'result': '0x1'}

    assert _relay_samples('eth_test', '200') == before + 1


@pytest.mark.unit
def test_relay_connection_error_is_measured_with_code_0():
    client = PrivateRelayClient(MagicMock(), URI('https://relay.example/rpc'), SIGNER_PRIVATE_KEY)
    before = _relay_samples('eth_test', '0')

    with (
        patch('blockchain.web3_extentions.private_relay.requests.post', side_effect=requests.ConnectionError('down')),
        pytest.raises(requests.ConnectionError),
    ):
        client._handle_post_request('eth_test', [])

    assert _relay_samples('eth_test', '0') == before + 1
