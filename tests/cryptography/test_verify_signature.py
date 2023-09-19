from cryptography.verify_signature import (
    compute_vs,
    verify_message_with_signature,
)
from tests.fixtures.signature_fixtures import deposit_messages, deposit_prefix


def test_valid_deposit_signature():
    for dm in deposit_messages:
        _is_vs_valid(dm)


def _is_vs_valid(msg):
    _vs = compute_vs(msg['signature']['v'], msg['signature']['s'])
    assert _vs == msg['signature']['_vs']


def test_deposit_messages_sign_check():
    for dm in deposit_messages:
        assert verify_message_with_signature(
            data=[deposit_prefix, dm['depositRoot'], dm['keysOpIndex'], dm['blockNumber'], dm['blockHash']],
            abi=['bytes32', 'bytes32', 'uint256', 'uint256', 'bytes32'],
            address=dm['guardianAddress'],
            vrs=(
                dm['signature']['v'],
                dm['signature']['r'],
                dm['signature']['s'],
            ),
        )
