import logging
from typing import Any, Callable, List

from blockchain.typings import Web3
from cryptography.verify_signature import recover_vs, verify_message_with_signature
from eth_account.account import VRS
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from transport.msg_types.deposit import DepositMessage
from transport.msg_types.pause import PauseMessage
from transport.msg_types.unvet import UnvetMessage
from utils.bytes import from_hex_string_to_bytes

logger = logging.getLogger(__name__)


def get_messages_sign_filter(web3: Web3) -> Callable:
    """Returns filter that checks message validity"""

    def check_messages(msg: DepositMessage | PauseMessage | UnvetMessage) -> bool:
        v, r, s = _vrs(msg)
        data, abi = _verification_data(web3, msg)

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
    if t == 'pause':
        return 'pause_message_verification_failed'
    elif t == 'unvet':
        return 'get_unvet_messages_sign_filter'
    elif t == 'deposit':
        return 'deposit_message_verification_failed'
    else:
        raise ValueError('Unsupported message type')


def _verification_data(web3: Web3, msg: DepositMessage | PauseMessage | UnvetMessage) -> tuple[List[Any], List[str]]:
    t = msg['type']
    if t == 'pause':
        prefix = web3.lido.deposit_security_module.get_pause_message_prefix()
        return _verification_data_pause(prefix, msg)
    elif t == 'unvet':
        prefix = web3.lido.deposit_security_module.get_unvet_message_prefix()
        return _verification_data_unvet(prefix, msg)
    elif t == 'deposit':
        prefix = web3.lido.deposit_security_module.get_attest_message_prefix()
        return _verification_data_deposit(prefix, msg)
    else:
        raise ValueError('Unsupported message type')


def _verification_data_deposit(prefix: bytes, msg: DepositMessage) -> tuple[List[Any], List[str]]:
    data = [prefix, msg['blockNumber'], msg['blockHash'], msg['depositRoot'], msg['stakingModuleId'], msg['nonce']]
    abi = ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256']
    return data, abi


def _verification_data_pause(prefix: bytes, msg: PauseMessage) -> tuple[List[Any], List[str]]:
    if msg.get('stakingModuleId', -1) != -1:
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
