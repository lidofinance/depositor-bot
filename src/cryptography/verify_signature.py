import logging
from typing import Any, List, Tuple

from eth_account import Account
from eth_account.account import VRS
from web3 import Web3

logger = logging.getLogger(__name__)


def compute_vs(v: int, s: str) -> str:
    """Returns aggregated _vs value."""
    if v < 27:
        if v in [0, 1]:
            v += 27
        else:
            msg = 'Signature invalid v byte.'
            logger.error({'msg': 'Signature invalid v byte.', 'data': str(v)})
            raise ValueError(msg)

    _vs = bytearray.fromhex(s[2:])
    if not v % 2:
        _vs[0] |= 0x80

    return '0x' + _vs.hex()


# Solidity function
#
# function recover(bytes32 hash, bytes32 r, bytes32 vs) internal pure returns (address) {
#        bytes32 s;
#        uint8 v;
#        assembly {
#            s := and(vs, 0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff)
#            v := add(shr(255, vs), 27)
#        }
#        return recover(hash, v, r, s);
#    }
def recover_vs(vs: str) -> tuple[VRS, VRS]:
    _vs = int.from_bytes(bytearray.fromhex(vs[2:]))
    s = _vs & 0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
    v = (_vs >> 255) + 27
    return v, s


def verify_message_with_signature(data: List[Any], abi: List[str], address: str, vrs: Tuple[VRS, VRS, VRS]) -> bool:
    """
    Check that message was correctly signed by provided address holder.
    """
    try:
        msg_hash = Web3.solidity_keccak(abi, data)
        recovered_address = Account._recover_hash(msg_hash, vrs=vrs)
    except Exception as error:
        logger.warning({'msg': 'Check signature failed.', 'error': str(error)})
        return False

    return address == recovered_address
