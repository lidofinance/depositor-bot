import logging
from typing import Any, List, Tuple

from eth_account import Account
from eth_account.account import VRS
from web3 import Web3

logger = logging.getLogger(__name__)

V_OFFSET = 27


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
    """
    Recovers v and s parameters of the signature from _vs field
    """
    # cut 0x
    _vs = int.from_bytes(bytearray.fromhex(vs[2:]))
    s = _vs & 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
    v = (_vs >> 255) + V_OFFSET
    return v, s


def compute_vs(v: int, s: str) -> str:
    """Returns aggregated _vs value."""
    if v < V_OFFSET and v not in [0, 1]:
        logger.error({'msg': 'Signature invalid v byte.', 'data': str(v)})
        raise ValueError('Signature invalid v byte.')
    if v < V_OFFSET:
        v += V_OFFSET
    _vs = bytearray.fromhex(s[2:])
    if not v % 2:
        _vs[0] |= 0x80

    return '0x' + _vs.hex()


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
