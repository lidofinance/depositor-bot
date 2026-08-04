import pytest

from cryptography.verify_signature import (
    compact_signature,
    compute_vs,
    guardian_signature_bytes,
    recover_vs,
    to_guardian_signature,
    verify_message_with_signature,
)
from tests.fixtures.signature_fixtures import (
    deposit_messages,
    deposit_prefix,
)
from transport.msg_types.common import _vrs
from transport.msg_types.deposit import DepositMessageSchema
from utils.bytes import bytes_to_hex_string


def test_deposit_schema():
    for dm in deposit_messages:
        assert DepositMessageSchema.is_valid(dm)


def test_recover_vs():
    for dm in deposit_messages:
        if 'v' in dm['signature']:
            expected_vs = compute_vs(dm['signature']['v'], dm['signature']['s'])
            assert expected_vs == dm['signature']['_vs']
            v, s = recover_vs(expected_vs)
            assert v == dm['signature']['v']
            assert hex(s) == dm['signature']['s']


def test_deposit_messages_sign_check():
    for dm in deposit_messages:
        vrs = _vrs(dm)
        assert verify_message_with_signature(
            data=[deposit_prefix, dm['depositRoot'], dm['keysOpIndex'], dm['blockNumber'], dm['blockHash']],
            abi=['bytes32', 'bytes32', 'uint256', 'uint256', 'bytes32'],
            address=dm['guardianAddress'],
            vrs=vrs,
        )


@pytest.mark.unit
def test_compact_signature_round_trip():
    """A 65-byte r||s||v blob must reduce to the same compact pair the council would have published."""
    r = bytes(range(32))
    s = (2**255 - 1).to_bytes(32, 'big')
    for v in (27, 28):
        compact_r, compact_vs = compact_signature(r + s + v.to_bytes(1, 'big'))
        assert compact_r == r
        assert bytes_to_hex_string(compact_vs) == compute_vs(v, bytes_to_hex_string(s))
        recovered_v, recovered_s = recover_vs(bytes_to_hex_string(compact_vs))
        assert recovered_v == v
        assert recovered_s == int.from_bytes(s, 'big')


@pytest.mark.unit
def test_compact_signature_accepts_normalised_v():
    """eth-account style v (0/1) is accepted, matching compute_vs."""
    r, s = bytes(range(32)), bytes(32)
    for v, expected_v in ((0, 27), (1, 28)):
        _, compact_vs = compact_signature(r + s + v.to_bytes(1, 'big'))
        assert recover_vs(bytes_to_hex_string(compact_vs))[0] == expected_v


@pytest.mark.unit
@pytest.mark.parametrize('length', [0, 64, 66])
def test_compact_signature_rejects_wrong_length(length):
    with pytest.raises(ValueError):
        compact_signature(bytes(length))


def test_guardian_signature_bytes_is_r_s_v():
    # Uses a fixture message that carries explicit v and s so we can assemble the expected 65 bytes.
    dm = next(m for m in deposit_messages if 'v' in m['signature'] and 's' in m['signature'])
    sig = dm['signature']
    blob = guardian_signature_bytes(sig['r'], sig['_vs'])

    expected = bytes.fromhex(sig['r'][2:]) + bytes.fromhex(sig['s'][2:]) + bytes([sig['v']])
    assert blob == expected
    assert len(blob) == 65


def test_to_guardian_signature_shape():
    guardian = '0x43464Fe06c18848a2E2e913194D64c1970f4326a'
    dm = next(m for m in deposit_messages if 'v' in m['signature'] and 's' in m['signature'])
    r, vs = dm['signature']['r'], dm['signature']['_vs']

    # DSMv4: compact (r, _vs) pair, guardian not included.
    assert to_guardian_signature(guardian, r, vs, delegated=False) == (r, vs)

    # DSMv5: (guardian, 65-byte blob).
    g, blob = to_guardian_signature(guardian, r, vs, delegated=True)
    assert g == guardian
    assert blob == guardian_signature_bytes(r, vs)
