import json

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_typing import HexStr
from web3 import Web3

from blockchain.web3_extentions.private_relay import PrivateRelayClient

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
