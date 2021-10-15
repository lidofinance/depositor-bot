from collections import namedtuple
from typing import List, Tuple

from web3 import Web3
from web3.auto import w3


SignedData = namedtuple(
    'SignedData',
    ['msg_hash', 'v', 'r', 's', 'signature'],
)


def sign_data(data: List[str], private_key: str) -> SignedData:
    hashed = keccak256_hash(''.join(data))
    signed = ecdsa_sign(hashed, private_key)
    return signed


def keccak256_hash(data: str) -> str:
    """Get keccak256 hash for data."""
    return Web3.keccak(hexstr=data)


def ecdsa_sign(hashed_data: str, private_key: int) -> SignedData:
    """
    Sign hashed data with the private key.

    Return the ecrecover-ready signed data.
    """
    signed_message = w3.eth.account.signHash(
        hashed_data, private_key=private_key
    )
    # ecrecover in Solidity expects v as a native uint8,
    # but r and s as left-padded bytes32
    return SignedData(
        msg_hash=Web3.toHex(signed_message.messageHash),
        v=signed_message.v,
        r=as_bytes32_left_padded(signed_message.r),
        s=as_bytes32_left_padded(signed_message.s),
        signature=Web3.toHex(signed_message.signature)
    )


def as_bytes32_left_padded(val: int) -> str:
    """Convert int to a left-padded hex bytes."""
    return Web3.toHex(Web3.toBytes(val).rjust(32, b'\0'))


def as_uint256(n: int) -> str:
    """Convert int to the uint256 string representation."""
    return Web3.toBytes(n).rjust(32, b'\0').hex()


def to_eip_2098(sign: SignedData) -> Tuple[str, str]:
    vs = (sign.v - 27) << 255 | int(sign.s, 16)
    return sign.r, hex(vs)
