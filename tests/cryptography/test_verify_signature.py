from cryptography.verify_signature import (
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
