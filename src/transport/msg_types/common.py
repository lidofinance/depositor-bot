import logging
from typing import Any, Callable, List

from cryptography.verify_signature import recover_vs, verify_message_with_signature
from eth_account.account import VRS
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from transport.msg_providers.rabbit import MessageType
from transport.msg_types.deposit import DepositMessage
from transport.msg_types.pause import PauseMessage
from transport.msg_types.ping import PingMessage
from transport.msg_types.unvet import UnvetMessage
from utils.bytes import from_hex_string_to_bytes

logger = logging.getLogger(__name__)

BotMessage = DepositMessage | PauseMessage | UnvetMessage | PingMessage


def get_messages_sign_filter(prefix) -> Callable:
    """Returns filter that checks message validity"""

    def check_messages(msg: DepositMessage | PauseMessage | UnvetMessage) -> bool:
        v, r, s = _vrs(msg)
        data, abi = _verification_data(prefix, msg)

        is_valid = verify_message_with_signature(
            data=data,
            abi=abi,
            address=msg['guardianAddress'],
            vrs=(v, r, s),
        )

        if not is_valid:
            label_name = _select_label(msg)
            logger.error({'msg': 'Message verification failed.', 'value': msg})
            UNEXPECTED_EXCEPTIONS.labels(label_name).inc()

        return is_valid

    return check_messages


def _vrs(msg: DepositMessage | PauseMessage | UnvetMessage) -> tuple[VRS, VRS, VRS]:
    vs = msg['signature']['_vs']
    r = msg['signature']['r']
    v, s = recover_vs(vs)
    return v, r, s


def _select_label(msg: DepositMessage | PauseMessage | UnvetMessage) -> str:
    t = msg['type']
    if t == MessageType.PAUSE:
        return 'pause_message_verification_failed'
    elif t == MessageType.UNVET:
        return 'unvet_message_verification_failed'
    elif t == MessageType.DEPOSIT:
        return 'deposit_message_verification_failed'
    else:
        raise ValueError('Unsupported message type')


def _verification_data(prefix: bytes, msg: DepositMessage | PauseMessage | UnvetMessage) -> tuple[List[Any], List[str]]:
    t = msg['type']
    if t == MessageType.PAUSE:
        return _verification_data_pause(prefix, msg)
    elif t == MessageType.UNVET:
        return _verification_data_unvet(prefix, msg)
    elif t == MessageType.DEPOSIT:
        return _verification_data_deposit(prefix, msg)
    else:
        raise ValueError('Unsupported message type')


def _verification_data_deposit(prefix: bytes, msg: DepositMessage) -> tuple[List[Any], List[str]]:
    data = [prefix, msg['blockNumber'], msg['blockHash'], msg['depositRoot'], msg['stakingModuleId'], msg['nonce']]
    abi = ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256']
    return data, abi


def _verification_data_pause(prefix: bytes, msg: PauseMessage) -> tuple[List[Any], List[str]]:
    if 'stakingModuleId' in msg:
        data = [prefix, msg['blockNumber'], msg['stakingModuleId']]
        abi = ['bytes32', 'uint256', 'uint256']
    else:
        data = [prefix, msg['blockNumber']]
        abi = ['bytes32', 'uint256']
    return data, abi


def _verification_data_unvet(prefix: bytes, msg: UnvetMessage) -> tuple[List[Any], List[str]]:
    data = [
        prefix,
        msg['blockNumber'],
        msg['blockHash'],
        msg['stakingModuleId'],
        msg['nonce'],
        from_hex_string_to_bytes(msg['operatorIds']),
        from_hex_string_to_bytes(msg['vettedKeysByOperator']),
    ]
    abi = ['bytes32', 'uint256', 'bytes32', 'uint256', 'uint256', 'bytes', 'bytes']
    return data, abi
