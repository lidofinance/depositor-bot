from unittest.mock import Mock

import pytest
from web3 import Web3

MODULE_ID = 1


@pytest.mark.unit
def test_deposited_keys_amount(base_deposit_strategy):
    depositable_eth = 100
    possible_deposits = depositable_eth // 32

    base_deposit_strategy.w3.lido.lido.get_depositable_ether = Mock(return_value=depositable_eth)
    base_deposit_strategy.w3.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=possible_deposits)

    assert base_deposit_strategy.deposited_keys_amount(MODULE_ID) == possible_deposits
    base_deposit_strategy.w3.lido.staking_router.get_staking_module_max_deposits_count.assert_called_once_with(
        MODULE_ID,
        depositable_eth,
    )


@pytest.mark.unit
def test_deposited_keys_amount_mellow(mellow_deposit_strategy):
    # Setup
    depositable_eth = 100
    possible_deposits = depositable_eth // 32
    vault_balance = 10

    mellow_deposit_strategy.w3.lido.simple_dvt_staking_strategy.vault_balance = Mock(return_value=vault_balance)
    mellow_deposit_strategy.w3.lido.lido.get_depositable_ether = Mock(return_value=depositable_eth)
    mellow_deposit_strategy.w3.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=possible_deposits)

    # Execution
    deposited_keys = mellow_deposit_strategy.deposited_keys_amount(MODULE_ID)

    # Verification
    assert deposited_keys == possible_deposits
    mellow_deposit_strategy.w3.lido.simple_dvt_staking_strategy.vault_balance.assert_called_once()
    mellow_deposit_strategy.w3.lido.staking_router.get_staking_module_max_deposits_count.assert_any_call(
        MODULE_ID,
        depositable_eth + vault_balance,
    )
    mellow_deposit_strategy.w3.lido.staking_router.get_staking_module_max_deposits_count.assert_any_call(
        MODULE_ID,
        Web3.to_wei(32 * possible_deposits, 'ether'),
    )
