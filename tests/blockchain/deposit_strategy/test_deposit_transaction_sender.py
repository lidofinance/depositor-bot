from unittest.mock import Mock

import pytest
from transport.msg_types.deposit import DepositMessage

MODULE_ID = 1


@pytest.mark.unit
def test_send_deposit_tx(cmds):
    cmds.w3.transaction.check = Mock(return_value=False)
    messages = [DepositMessage(
        type='deposit',
        depositRoot='',
        nonce=1,
        blockNumber=1,
        blockHash='',
        guardianAddress='0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        stakingModuleId=1,
        signature={
            'r': '0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116',
            's': '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0',
            'v': 27,
        },
        app={'version': '1.0.3', 'name': 'lido-council-daemon'},
    )]
    cmds._prepare_signs_for_deposit = Mock(return_value=tuple())
    cmds.is_gas_price_ok = Mock(return_value=True)
    cmds.deposited_keys_amount = Mock(return_value=True)
    assert not cmds.prepare_and_send(messages, False)

    cmds.w3.transaction.check = Mock(return_value=True)
    cmds.w3.transaction.send = Mock(return_value=True)
    assert cmds.prepare_and_send(messages, False)
    cmds.w3.transaction.send = Mock(return_value=False)
    assert not cmds.prepare_and_send(messages, False)
