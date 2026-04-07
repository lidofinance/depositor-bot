import json

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from blockchain.web3_extentions.private_relay import PrivateRelayClient
from web3 import Web3


SIGNER_PRIVATE_KEY = '0x' + 'aa' * 32


@pytest.mark.unit
def test_flashbots_signature_signs_hash_bytes():
    """
    The X-Flashbots-Signature must be personal_sign(keccak256(body)).
    That means encode_defunct receives the raw 32-byte hash (primitive=),
    NOT the hex-string representation of the hash (text=).
    """
    signer = Account.from_key(SIGNER_PRIVATE_KEY)
    method = 'eth_sendPrivateTransaction'
    params = [{'tx': '0xdeadbeef'}]

    body = {
        'jsonrpc': '2.0',
        'id': '1',
        'method': method,
        'params': params,
    }

    body_hash = Web3.keccak(text=json.dumps(body))

    # Correct: sign the 32-byte hash
    correct_message = encode_defunct(primitive=body_hash)
    correct_sig = signer.sign_message(correct_message).signature.hex()

    # Wrong: sign the hex-string representation of the hash (old broken behaviour)
    wrong_message = encode_defunct(text=body_hash.hex())
    wrong_sig = signer.sign_message(wrong_message).signature.hex()

    assert correct_sig != wrong_sig, 'The two approaches must differ so this test is meaningful'

    headers, signature, _ = PrivateRelayClient._get_rpc_request(method, params, signer)

    signing_address, relay_sig = signature.split(':')
    assert signing_address == signer.address
    assert relay_sig == correct_sig, 'Relay signature must match personal_sign(keccak256(body))'
    assert relay_sig != wrong_sig
    assert headers['X-Flashbots-Signature'] == signature
