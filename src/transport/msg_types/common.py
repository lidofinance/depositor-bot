import logging
from collections.abc import Callable
from typing import Any, cast

from eth_account.account import VRS

from cryptography.verify_signature import recover_vs, verify_message_with_signature
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from transport.msg_providers.rabbit import MessageType
from transport.msg_types.deposit import DepositMessage
from transport.msg_types.pause import PauseMessage
from transport.msg_types.ping import PingMessage
from transport.msg_types.unvet import UnvetMessage
from utils.bytes import from_hex_string_to_bytes

logger = logging.getLogger(__name__)

BotMessage = DepositMessage | PauseMessage | UnvetMessage | PingMessage


def get_messages_sign_filter(prefix: bytes, delegated: bool = False) -> Callable:
    """Returns a filter that checks a message's guardian signature.

    ``delegated`` selects the signing scheme:

    - ``False`` (DSMv4, guardians are EOAs): the digest is ``prefix || fields`` and the signature must
      recover to ``guardianAddress`` (the guardian EOA).
    - ``True`` (DSMv5 / EDF, guardians are contracts): the digest folds the guardian contract address
      in right after the prefix, and the signature must recover to the guardian's delegate EOA
      (``guardianDelegate``) — the off-chain equivalent of the on-chain ERC-1271 check against
      ``getDelegate()``.
    """

    def check_messages(msg: DepositMessage | PauseMessage | UnvetMessage) -> bool:
        v, r, s = _vrs(msg)
        data, abi = _verification_data(prefix, msg, delegated)
        # Under delegation the signer is the guardian's delegate EOA (carried on the message by the
        # onchain transport); fall back to guardianAddress if it is absent (e.g. legacy transports).
        expected_signer = cast(dict, msg).get('guardianDelegate', msg['guardianAddress']) if delegated else msg['guardianAddress']

        is_valid = verify_message_with_signature(
            data=data,
            abi=abi,
            address=expected_signer,
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


def _verification_data(prefix: bytes, msg: BotMessage, delegated: bool = False) -> tuple[list[Any], list[str]]:
    t = msg['type']
    if t == MessageType.PAUSE:
        data, abi = _verification_data_pause(prefix, cast(PauseMessage, msg))
    elif t == MessageType.UNVET:
        data, abi = _verification_data_unvet(prefix, cast(UnvetMessage, msg))
    elif t == MessageType.DEPOSIT:
        data, abi = _verification_data_deposit(prefix, cast(DepositMessage, msg))
    else:
        raise ValueError('Unsupported message type')

    if delegated:
        # DSMv5 binds the digest to the guardian contract: keccak(prefix, guardian, ...fields).
        # `address` packs to 20 bytes under solidity_keccak, matching the contract's abi.encodePacked.
        data.insert(1, msg['guardianAddress'])
        abi.insert(1, 'address')
    return data, abi


def _verification_data_deposit(prefix: bytes, msg: DepositMessage) -> tuple[list[Any], list[str]]:
    data = [prefix, msg['blockNumber'], msg['blockHash'], msg['depositRoot'], msg['stakingModuleId'], msg['nonce']]
    abi = ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256']
    return data, abi


def _verification_data_pause(prefix: bytes, msg: PauseMessage) -> tuple[list[Any], list[str]]:
    data = [prefix, msg['blockNumber']]
    abi = ['bytes32', 'uint256']
    return data, abi


def _verification_data_unvet(prefix: bytes, msg: UnvetMessage) -> tuple[list[Any], list[str]]:
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
