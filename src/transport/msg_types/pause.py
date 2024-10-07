import logging
from typing import TypedDict

from schema import And, Schema
from transport.msg_types.base import ADDRESS_REGREX, Signature, SignatureSchema

logger = logging.getLogger(__name__)

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
PauseMessageSchema = Schema(
    {
        'type': And(str, lambda t: t in ('pause',)),
        'blockNumber': int,
        'guardianAddress': And(str, ADDRESS_REGREX.validate),
        'signature': SignatureSchema,
        # 'stakingModuleId': int
    },
    ignore_extra_keys=True,
)


class PauseMessage(TypedDict):
    type: str
    blockNumber: int
    guardianAddress: str
    signature: Signature
    stakingModuleId: int
    transport: str
    chain_id: int
