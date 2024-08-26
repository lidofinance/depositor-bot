import re
from typing import TypedDict

from eth_account.account import VRS
from schema import And, Optional, Regex, Schema

HASH_REGREX = Regex('^0x[0-9,A-F]{64}$', flags=re.IGNORECASE)
ADDRESS_REGREX = Regex('^0x[0-9,A-F]{40}$', flags=re.IGNORECASE)
HEX_BYTES_REGREX = Regex('^0x[0-9,A-F]*$', flags=re.IGNORECASE)

# v and s to be removed in future in favor of short signatures
SignatureSchema = Schema(
    {
        Optional('v'): int,
        'r': And(str, HASH_REGREX.validate),
        Optional('s'): And(str, HASH_REGREX.validate),
        '_vs': And(str, HASH_REGREX.validate),
    },
    ignore_extra_keys=True,
)


class Signature(TypedDict):
    v: VRS
    r: VRS
    s: VRS
    _vs: str
