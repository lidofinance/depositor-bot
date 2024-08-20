from cryptography.verify_signature import verify_message_with_signature, recover_vs
from tests.utils.signature import compute_vs
from transport.msg_types.common import _vrs
from transport.msg_types.deposit import DepositMessageSchema

from tests.fixtures.signature_fixtures import (
    deposit_messages,
    deposit_prefix,
)


def test_recover_vs():
    for dm in deposit_messages:
        if 'v' in dm['signature']:
            expected_vs = compute_vs(dm['signature']['v'], dm['signature']['s'])
            assert expected_vs == dm['signature']['_vs']
            v, s = recover_vs(expected_vs)
            assert v == dm['signature']['v']
            assert hex(s) == dm['signature']['s']


def test_deposit_messages_sign_check():
    for dm in deposit_messages:
        assert DepositMessageSchema.is_valid(dm)
        vrs = _vrs(dm)
        assert verify_message_with_signature(
            data=[deposit_prefix, dm['depositRoot'], dm['keysOpIndex'], dm['blockNumber'], dm['blockHash']],
            abi=['bytes32', 'bytes32', 'uint256', 'uint256', 'bytes32'],
            address=dm['guardianAddress'],
            vrs=vrs,
        )
