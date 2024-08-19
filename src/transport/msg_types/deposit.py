import logging
from typing import Callable, TypedDict

from blockchain.typings import Web3
from cryptography.verify_signature import recover_vs, verify_message_with_signature
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from schema import And, Schema
from transport.msg_types.base import ADDRESS_REGREX, HASH_REGREX, Signature, SignatureSchema

logger = logging.getLogger(__name__)

"""
Deposit msg example
{
    "type": "deposit",
    "depositRoot": "0xbc034415ccde0596f39095fd2d99c2fa1e335de3f70b34dcd78e2ab21fa0c5e8",
    "nonce": 16,
    "blockNumber": 5737984,
    "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
    "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
    "guardianIndex": 8,
    "signature": {
        "r": "0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116",
        "s": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
        "_vs": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
        "recoveryParam": 0,
        "v": 27
    },
    "app": {
        "version": "1.0.3",
        "name": "lido-council-daemon"
    }
}
"""
DepositMessageSchema = Schema(
    {
        'type': And(str, lambda t: t in ('deposit',)),
        'depositRoot': And(str, HASH_REGREX.validate),
        'nonce': int,
        'blockNumber': int,
        'blockHash': And(str, HASH_REGREX.validate),
        'guardianAddress': And(str, ADDRESS_REGREX.validate),
        'signature': SignatureSchema,
        'stakingModuleId': int,
    },
    ignore_extra_keys=True,
)


class DepositMessage(TypedDict):
    type: str
    depositRoot: str
    nonce: int
    blockNumber: int
    blockHash: str
    guardianAddress: str
    signature: Signature
    stakingModuleId: int
    app: dict


def get_deposit_messages_sign_filter(web3: Web3) -> Callable:
    """Returns filter that checks message validity"""

    def check_deposit_messages(msg: DepositMessage) -> bool:
        deposit_prefix = web3.lido.deposit_security_module.get_attest_message_prefix()

        vs = msg['signature']['_vs']
        if vs is None:
            v = msg['signature']['v']
            r = msg['signature']['r']
            s = msg['signature']['s']
        else:
            r = msg['signature']['r']
            v, s = recover_vs(vs)

        verified = verify_message_with_signature(
            data=[deposit_prefix, msg['blockNumber'], msg['blockHash'], msg['depositRoot'], msg['stakingModuleId'], msg['nonce']],
            abi=['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
            address=msg['guardianAddress'],
            vrs=(v, r, s),
        )

        if not verified:
            logger.error({'msg': 'Message verification failed.', 'value': msg})
            UNEXPECTED_EXCEPTIONS.labels('deposit_message_verification_failed').inc()

        return verified

    return check_deposit_messages
