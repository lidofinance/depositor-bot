import logging
from typing import TypedDict

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
