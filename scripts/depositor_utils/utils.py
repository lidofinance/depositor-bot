import datetime
import functools
import os
from collections import namedtuple
from typing import Optional

from web3 import Web3
from web3.auto import w3

from .constants import PRIVATE_KEY_ENV_VARIABLE


def cache(ttl=datetime.timedelta(minutes=10)):
    def wrap(func):
        time, value = None, None

        @functools.wraps(func)
        def wrapped(*args, **kw):
            nonlocal time
            nonlocal value

            now = datetime.datetime.now()
            if not time or now - time > ttl:
                value = func(*args, **kw)
                time = now
            return value

        return wrapped

    return wrap


def keccak256_hash(data: str) -> str:
    """Get keccak256 hash for data."""
    return Web3.keccak(hexstr=data)


def get_private_key() -> Optional[int]:
    """Return depositor bot private key."""
    key = os.getenv(PRIVATE_KEY_ENV_VARIABLE, None)
    if key is None:
        return

    if not key.isdigit():
        raise TypeError('private key should be a number.')

    return int(key)


SignedData = namedtuple(
    'SignedData',
    ['msg_hash', 'v', 'r', 's', 'signature']
)


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


def as_bytes32(data: str) -> str:
    """Convert string to the bytes32 string representation."""
    return data.rjust(32, '0')


def as_uint256(n: int) -> str:
    """Convert int to the uint256 string representation."""
    return Web3.toBytes(n).rjust(32, b'\0').hex()
