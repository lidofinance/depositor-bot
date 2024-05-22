import re
from typing import TypedDict

from schema import And, Regex, Schema

HASH_REGREX = Regex('^0x[0-9,A-F]{64}$', flags=re.IGNORECASE)
ADDRESS_REGREX = Regex('^0x[0-9,A-F]{40}$', flags=re.IGNORECASE)
HEX_BYTES_REGREX = Regex('^0x[0-9,A-F]*$', flags=re.IGNORECASE)

SignatureSchema = Schema(
    {
        'v': int,
        'r': And(str, HASH_REGREX.validate),
        's': And(str, HASH_REGREX.validate),
    },
    ignore_extra_keys=True,
)


class Signature(TypedDict):
    v: int
    r: str
    s: str
