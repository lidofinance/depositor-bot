import pytest
from transport.msg_types.deposit import DepositMessageSchema
from transport.msg_types.ping import to_check_sum_address


@pytest.mark.unit
def test_to_check_sum_address():
    council_message = {'guardianAddress': '0x43464fe06c18848a2E2e913194d64c1970f4326a'}

    to_check_sum_address(council_message)

    assert council_message['guardianAddress'] == '0x43464Fe06c18848a2E2e913194D64c1970f4326a'


@pytest.mark.unit
def test_check_depositor_schema_positive():
    msg = {
        "type": "deposit",
        "depositRoot": "0xbc034415ccde0596f39095fd2d99c2fa1e335de3f70b34dcd78e2ab21fa0c5e8",
        "nonce": 16,
        "blockNumber": 5737984,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
        "signature": {
            "r": "0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116",
            "s": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "_vs": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "recoveryParam": 0,
            "v": 27
        },
        "app": {
            "version": "1.0.3",
            "name": "lido-council-daemon"
        },
        'stakingModuleId': 2,
    }
    assert DepositMessageSchema.is_valid(msg)


@pytest.mark.unit
def test_check_depositor_schema_negative():
    # vs parameter removed
    msg = {
        "type": "deposit",
        "depositRoot": "0xbc034415ccde0596f39095fd2d99c2fa1e335de3f70b34dcd78e2ab21fa0c5e8",
        "nonce": 16,
        "blockNumber": 5737984,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
        "signature": {
            "r": "0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116",
            "s": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "recoveryParam": 0,
            "v": 27
        },
        "app": {
            "version": "1.0.3",
            "name": "lido-council-daemon"
        },
        'stakingModuleId': 2,
    }
    assert not DepositMessageSchema.is_valid(msg)
