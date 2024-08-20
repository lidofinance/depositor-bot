from cryptography.verify_signature import V_OFFSET


def compute_vs(v: int, s: str) -> str:
    """Returns aggregated _vs value."""
    if v < V_OFFSET and v not in [0, 1]:
        raise ValueError('Signature invalid v byte.')
    if v < V_OFFSET:
        v += V_OFFSET
    _vs = bytearray.fromhex(s[2:])
    if not v % 2:
        _vs[0] |= 0x80

    return '0x' + _vs.hex()
