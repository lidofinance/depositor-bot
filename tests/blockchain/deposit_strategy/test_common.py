import pytest

from blockchain.deposit_strategy.deposit_transaction_sender import Sender


@pytest.fixture
def deposit_message():
    yield {
        'type': 'deposit',
        'depositRoot': '0x64dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b',
        'nonce': 12,
        'blockNumber': 10,
        'blockHash': '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
        'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        'guardianIndex': 8,
        'stakingModuleId': 1,
        'signature': {
            'r': '0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116',
            's': '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0',
            '_vs': '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0',
            'recoveryParam': 0,
            'v': 27,
        },
        'app': {'version': '1.0.3', 'name': 'lido-council-daemon'},
    }


_R = '0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116'
_VS = '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0'


@pytest.fixture
def second_council():
    # guardianAddress sorts *before* deposit_message's (0x1346… < 0x4346…).
    yield {
        'guardianAddress': '0x13464Fe06c18848a2E2e913194D64c1970f4326a',
        'signature': {'r': _R, 's': _VS, '_vs': _VS, 'recoveryParam': 0, 'v': 27},
    }


@pytest.mark.unit
def test_prepare_signs_for_deposit_v4(deposit_message, second_council):
    # DSMv4: compact (r, _vs) pairs, sorted ascending by guardian address.
    expected = ((_R, _VS), (_R, _VS))

    assert Sender._prepare_signs_for_deposit([second_council, deposit_message], delegated=False) == expected
    assert Sender._prepare_signs_for_deposit([deposit_message, second_council], delegated=False) == expected


@pytest.mark.unit
def test_prepare_signs_for_deposit_v5_delegated(deposit_message, second_council):
    # DSMv5: (guardian_contract, 65-byte r||s||v) tuples, sorted ascending by guardian address.
    # _vs has a clear high bit here, so v == 27 (0x1b) and s == _vs.
    sig_bytes = bytes.fromhex(_R[2:]) + bytes.fromhex(_VS[2:]) + bytes([27])
    expected = (
        ('0x13464Fe06c18848a2E2e913194D64c1970f4326a', sig_bytes),
        ('0x43464Fe06c18848a2E2e913194D64c1970f4326a', sig_bytes),
    )

    assert Sender._prepare_signs_for_deposit([second_council, deposit_message], delegated=True) == expected
    assert Sender._prepare_signs_for_deposit([deposit_message, second_council], delegated=True) == expected
    # Each blob is exactly r(32) + s(32) + v(1).
    assert all(len(sig) == 65 for _, sig in expected)
