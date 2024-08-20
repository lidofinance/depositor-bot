from cryptography.verify_signature import verify_message_with_signature
from transport.msg_types.common import _vrs
from transport.msg_types.deposit import DepositMessageSchema

from tests.fixtures.signature_fixtures import (
    deposit_messages,
    deposit_prefix,
)


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
