import logging
from typing import Any, List, Tuple

from eth_account import Account
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


def verify_message_with_signature(data: List[Any], abi: List[str], address: str, vrs: Tuple[int, str, str]) -> bool:
    """
    Check that message was correctly signed by provided address holder.
    """
    try:
        msg_hash = Web3.solidityKeccak(abi, data)
        recovered_address = Account.recoverHash(msg_hash, vrs=vrs)
    except Exception as error:
        logger.warning({'msg': 'Check signature failed.', 'error': str(error)})
        return False

    return address == recovered_address
