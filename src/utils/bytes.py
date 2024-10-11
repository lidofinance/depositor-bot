from eth_typing import HexStr


def from_hex_string_to_bytes(hex_string: str) -> bytes:
    if hex_string.startswith('0x'):
        return bytes.fromhex(hex_string[2:])
    return bytes.fromhex(hex_string)


def bytes_to_hex_string(b: bytes) -> HexStr:
    return HexStr('0x' + b.hex())
