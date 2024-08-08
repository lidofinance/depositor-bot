from unittest.mock import Mock

import pytest

import variables
from blockchain.deposit_strategy.deposit_transaction_sender import Sender, MellowSender
from blockchain.typings import Web3
from transport.msg_types.deposit import DepositMessage

MODULE_ID = 1


@pytest.mark.unit
def test_send_deposit_tx_not_mellow(deposit_transaction_sender: Sender):
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
    deposit_transaction_sender._sender_checks = Mock(return_value=True)
    assert not deposit_transaction_sender.prepare_and_send(MODULE_ID, messages, False)
    assert deposit_transaction_sender._w3.lido.deposit_security_module.deposit_buffered_ether.called

    deposit_transaction_sender._w3.transaction.check = Mock(return_value=True)
    deposit_transaction_sender._w3.transaction.send = Mock(return_value=True)
    assert deposit_transaction_sender.prepare_and_send(MODULE_ID, messages, False)
    assert deposit_transaction_sender._w3.lido.deposit_security_module.deposit_buffered_ether.called

@pytest.mark.unit
def test_is_mellow_depositable(deposit_transaction_mellow_sender: MellowSender):
    deposit_transaction_mellow_sender._gas_price_calculator._get_pending_base_fee = Mock(return_value=10)
    deposit_transaction_mellow_sender._w3.lido.lido.get_depositable_ether = Mock(return_value=Web3.to_wei(0.5, 'ether'))
    deposit_transaction_mellow_sender._w3.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=10)
    variables.MELLOW_CONTRACT_ADDRESS = None
    assert not deposit_transaction_mellow_sender._sender_checks(1)

    variables.MELLOW_CONTRACT_ADDRESS = '0x1'
    deposit_transaction_mellow_sender._w3.lido.lido.get_buffered_ether = Mock(return_value=Web3.to_wei(1, 'ether'))
    deposit_transaction_mellow_sender._w3.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth = Mock(return_value=Web3.to_wei(1, 'ether'))
    deposit_transaction_mellow_sender._w3.lido.simple_dvt_staking_strategy.staking_module_contract.get_staking_module_id = Mock(return_value=1)
    assert not deposit_transaction_mellow_sender._sender_checks(2)

    deposit_transaction_mellow_sender._w3.lido.simple_dvt_staking_strategy.vault_balance = Mock(return_value=Web3.to_wei(0.5, 'ether'))
    assert not deposit_transaction_mellow_sender._sender_checks(2)

    deposit_transaction_mellow_sender._w3.lido.simple_dvt_staking_strategy.vault_balance = Mock(return_value=Web3.to_wei(1.4, 'ether'))
    assert deposit_transaction_mellow_sender._sender_checks(1)

    deposit_transaction_mellow_sender._w3.lido.lido.get_buffered_ether = Mock(return_value=Web3.to_wei(0.5, 'ether'))
    deposit_transaction_mellow_sender._w3.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth = Mock(return_value=Web3.to_wei(1, 'ether'))
    assert not deposit_transaction_mellow_sender._sender_checks(1)
