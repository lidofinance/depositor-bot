import logging

from schema import And, Schema
from transport.msg_types.base import ADDRESS_REGREX, Metadata
from web3 import Web3

logger = logging.getLogger(__name__)

PingMessageSchema = Schema(
    {
        'type': And(str, lambda t: t in ('ping',)),
        'blockNumber': int,
        'guardianAddress': And(str, ADDRESS_REGREX.validate),
    },
    ignore_extra_keys=True,
)


class PingMessage(Metadata):
    blockNumber: int
    guardianAddress: str


def to_check_sum_address(msg: dict):
    msg['guardianAddress'] = Web3.to_checksum_address(msg['guardianAddress'])
    return msg
