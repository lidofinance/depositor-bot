import logging
from typing import Callable, TypedDict

from schema import Schema, And

from cryptography.verify_signature import verify_message_with_signature
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from transport.msg_types.base import ADDRESS_REGREX, SignatureSchema, Signature, HASH_REGREX


logger = logging.getLogger(__name__)


UnvetMessageSchema = Schema({
    'type': And(str, lambda t: t in ('unvet',)),
    'blockNumber': int,
    'blockHash': And(str, HASH_REGREX),
    'guardianAddress': And(str, ADDRESS_REGREX),
    'signature': SignatureSchema,
    'stakingModuleId': int,
    'operatorIds': list[int],
    'vettedKeysByOperator': list[int],
}, ignore_extra_keys=True)


class UnvetMessage(TypedDict):
    type: str
    blockNumber: int
    blockHash: str
    guardianAddress: str
    signature: Signature
    stakingModuleId: int
    nonce: int
    operatorIds: list[int]
    vettedKeysByOperator: list[int]


def get_unvet_messages_sign_filter(unvet_prefix: bytes) -> Callable:
    def check_unvet_message(msg: UnvetMessage) -> bool:
        verified = verify_message_with_signature(
            data=[
                unvet_prefix,
                msg['blockNumber'],
                msg['blockHash'],
                msg['stakingModuleId'],
                msg['nonce'],
                msg['operatorIds'],
                msg['vettedKeysByOperator'],
            ],
            abi=['bytes32', 'uint256', 'bytes32', 'uint256', 'number[]', 'number[]'],
            address=msg['guardianAddress'],
            vrs=(
                msg['signature']['v'],
                msg['signature']['r'],
                msg['signature']['s'],
            ),
        )

        if not verified:
            logger.error({'msg': 'Message verification failed.', 'value': msg})
            UNEXPECTED_EXCEPTIONS.labels('get_unvet_messages_sign_filter').inc()

        return verified

    return check_unvet_message
