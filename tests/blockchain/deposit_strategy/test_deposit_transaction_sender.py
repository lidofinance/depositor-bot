from unittest.mock import Mock

import pytest

from transport.msg_types.deposit import DepositMessage

MODULE_ID = 1


@pytest.mark.unit
def test_send_deposit_tx_not_mellow(deposit_transaction_sender):
    deposit_transaction_sender._w3.transaction.check = Mock(return_value=False)
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
    deposit_transaction_sender._prepare_signs_for_deposit = Mock(return_value=tuple())
    assert not deposit_transaction_sender.prepare_and_send(messages, False, False)
    assert deposit_transaction_sender._w3.lido.deposit_security_module.deposit_buffered_ether.called

    deposit_transaction_sender._w3.transaction.check = Mock(return_value=True)
    deposit_transaction_sender._w3.transaction.send = Mock(return_value=True)
    assert deposit_transaction_sender.prepare_and_send(messages, False, False)
    assert deposit_transaction_sender._w3.lido.deposit_security_module.deposit_buffered_ether.called
