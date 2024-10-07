import logging
from typing import TypedDict

from eth_typing import Hash32
from schema import And, Schema
from transport.msg_types.base import ADDRESS_REGREX, HASH_REGREX, HEX_BYTES_REGREX, Signature, SignatureSchema

logger = logging.getLogger(__name__)

UnvetMessageSchema = Schema(
    {
        'type': And(str, lambda t: t in ('unvet',)),
        'blockNumber': int,
        'blockHash': And(str, HASH_REGREX.validate),
        'guardianAddress': And(str, ADDRESS_REGREX.validate),
        'signature': SignatureSchema,
        'stakingModuleId': int,
        'operatorIds': And(str, HEX_BYTES_REGREX.validate),
        'vettedKeysByOperator': And(str, HEX_BYTES_REGREX.validate),
    },
    ignore_extra_keys=True,
)


class UnvetMessage(TypedDict):
    type: str
    blockNumber: int
    blockHash: Hash32
    guardianAddress: str
    signature: Signature
    stakingModuleId: int
    nonce: int
    operatorIds: str
    vettedKeysByOperator: str
    transport: str
    chain_id: int
