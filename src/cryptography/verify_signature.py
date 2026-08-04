import logging
from typing import Any

from eth_account import Account
from eth_account.account import VRS
from web3 import Web3

from utils.bytes import bytes_to_hex_string, from_hex_string_to_bytes

logger = logging.getLogger(__name__)

V_OFFSET = 27
SIGNATURE_LENGTH = 65


def guardian_signature_bytes(r: str, vs: str) -> bytes:
    """Builds the 65-byte ``r || s || v`` signature blob for a DSMv5 ``GuardianSignature``.

    Council messages carry the compact ``(r, _vs)`` pair. DSMv5 verifies the guardian signature via
    ERC-1271 → ``ECDSA.recover``, which OpenZeppelin expects as ``r(32) || s(32) || v(1)`` (v is 27/28).
    This unpacks ``_vs`` back into ``s`` and ``v`` and concatenates — mirroring the daemon's
    ``concat([r, s, toBeHex(v, 1)])``.
    """
    v, s = recover_vs(vs)
    return from_hex_string_to_bytes(r) + int(s).to_bytes(32, 'big') + int(v).to_bytes(1, 'big')


def to_guardian_signature(guardian: str, r: str, vs: str, delegated: bool) -> tuple[str, str] | tuple[str, bytes]:
    """Shapes one guardian signature for the DSM call, version-aware.

    - DSMv5 (``delegated``): ``(guardian_contract, 65-byte r||s||v blob)`` for ERC-1271 verification.
    - DSMv4: the compact ``(r, _vs)`` pair recovered on-chain to the guardian EOA.
    """
    if delegated:
        return (guardian, guardian_signature_bytes(r, vs))
    return (r, vs)


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


def compact_signature(signature: bytes) -> tuple[bytes, bytes]:
    """Splits a flat 65-byte ``r || s || v`` signature into the compact ``(r, _vs)`` pair.

    Council v5 publishes Data Bus messages with the signature as a single ``bytes`` blob — the shape
    DSMv5 verifies through ERC-1271. The bot keeps signatures in the compact ``(r, _vs)`` form
    everywhere else (RabbitMQ transport, sign filter, DSMv4 submission), so blobs are normalised on
    parse and a single representation travels downstream. The conversion is lossless: ``_vs`` is ``s``
    with the parity of ``v`` folded into its top bit.
    """
    if len(signature) != SIGNATURE_LENGTH:
        raise ValueError(f'Guardian signature must be {SIGNATURE_LENGTH} bytes, got {len(signature)}.')
    r, s, v = signature[:32], signature[32:64], signature[64]
    # Reuses compute_vs so the packing rule (and its v validation) has one implementation.
    return r, from_hex_string_to_bytes(compute_vs(v, bytes_to_hex_string(s)))


def verify_message_with_signature(data: list[Any], abi: list[str], address: str, vrs: tuple[VRS, VRS, VRS]) -> bool:
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
