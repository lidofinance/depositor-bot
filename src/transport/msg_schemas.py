import logging
import re
from typing import Callable, TypedDict

from schema import Regex, Schema, And
from web3 import Web3

from cryptography.verify_signature import verify_message_with_signature
from metrics.metrics import UNEXPECTED_EXCEPTIONS

logger = logging.getLogger(__name__)


HASH_REGREX = Regex('^0x[0-9,A-F]{64}$', flags=re.IGNORECASE)
ADDRESS_REGREX = Regex('^0x[0-9,A-F]{40}$', flags=re.IGNORECASE)

SignatureSchema = Schema({
    'v': int,
    'r': And(str, HASH_REGREX),
    's': And(str, HASH_REGREX),
}, ignore_extra_keys=True)


class Signature(TypedDict):
    v: int
    r: str
    s: str


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
DepositMessageSchema = Schema({
    'type': And(str, lambda t: t in ('deposit',)),
    'depositRoot': And(str, HASH_REGREX),
    'nonce': int,
    'blockNumber': int,
    'blockHash': And(str, HASH_REGREX),
    'guardianAddress': And(str, ADDRESS_REGREX),
    'signature': SignatureSchema,
    'stakingModuleId': int
}, ignore_extra_keys=True)


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


def get_deposit_messages_sign_filter(deposit_prefix: bytes) -> Callable:
    """Returns filter that checks message validity"""
    def check_deposit_messages(msg: DepositMessage) -> bool:
        verified = verify_message_with_signature(
            data=[deposit_prefix, msg['blockNumber'], msg['blockHash'], msg['depositRoot'], msg['stakingModuleId'], msg['nonce']],
            abi=['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
            address=msg['guardianAddress'],
            vrs=(
                msg['signature']['v'],
                msg['signature']['r'],
                msg['signature']['s'],
            ),
        )

        if not verified:
            logger.error({'msg': 'Message verification failed.', 'value': msg})
            UNEXPECTED_EXCEPTIONS.labels('deposit_message_verification_failed').inc()

        return verified

    return check_deposit_messages


"""
Pause msg example:
{
    "blockHash": "0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c",
    "blockNumber": 5669490,
    "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
    "guardianIndex": 0,
    "signature": {
        "_vs": "0xd4933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
        "r": "0xbaa668505cd496caaf7117dd074338197200175057909ab73a04463656bdb0fa",
        "recoveryParam": 1,
        "s": "0x54933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
        "v": 28
    },
    "type": "pause"
}
"""
PauseMessageSchema = Schema({
    'type': And(str, lambda t: t in ('pause',)),
    'blockNumber': int,
    'guardianAddress': And(str, ADDRESS_REGREX),
    'signature': SignatureSchema,
    'stakingModuleId': int
}, ignore_extra_keys=True)


class PauseMessage(TypedDict):
    type: str
    blockNumber: int
    guardianAddress: str
    signature: Signature
    stakingModuleId: int


def get_pause_messages_sign_filter(pause_prefix: bytes) -> Callable:
    def check_pause_message(msg: PauseMessage) -> bool:
        verified = verify_message_with_signature(
            data=[pause_prefix, msg['blockNumber'], msg['stakingModuleId']],
            abi=['bytes32', 'uint256', 'uint256'],
            address=msg['guardianAddress'],
            vrs=(
                msg['signature']['v'],
                msg['signature']['r'],
                msg['signature']['s'],
            ),
        )

        if not verified:
            logger.error({'msg': 'Message verification failed.', 'value': msg})
            UNEXPECTED_EXCEPTIONS.labels('pause_message_verification_failed').inc()

        return verified

    return check_pause_message


PingMessageSchema = Schema({
    'type': And(str, lambda t: t in ('ping',)),
    'blockNumber': int,
    'guardianAddress': And(str, ADDRESS_REGREX),
    'stakingModuleIds': [int]
}, ignore_extra_keys=True)


def to_check_sum_address(msg: dict):
    msg['guardianAddress'] = Web3.to_checksum_address(msg['guardianAddress'])
    return msg
