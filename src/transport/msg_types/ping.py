import logging

from schema import Schema, And
from web3 import Web3

from transport.msg_types.base import ADDRESS_REGREX


logger = logging.getLogger(__name__)


PingMessageSchema = Schema({
    'type': And(str, lambda t: t in ('ping',)),
    'blockNumber': int,
    'guardianAddress': And(str, ADDRESS_REGREX),
    'stakingModuleIds': [int]
}, ignore_extra_keys=True)


def to_check_sum_address(msg: dict):
    msg['guardianAddress'] = Web3.to_checksum_address(msg['guardianAddress'])
    return msg
