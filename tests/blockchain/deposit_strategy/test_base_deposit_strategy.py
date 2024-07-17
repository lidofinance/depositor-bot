from unittest.mock import Mock

import pytest
from blockchain.deposit_strategy.base_deposit_strategy import BaseDepositStrategy

MODULE_ID = 1


@pytest.fixture
def base_deposit_strategy(web3_lido_unit):
    yield BaseDepositStrategy(web3_lido_unit)


@pytest.mark.unit
def test_get_possible_deposits_amount(base_deposit_strategy):
    depositable_eth = 100
    possible_deposits = depositable_eth // 32

    base_deposit_strategy.w3.lido.lido.get_depositable_ether = Mock(return_value=depositable_eth)
    base_deposit_strategy.w3.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=possible_deposits)

    assert base_deposit_strategy.deposited_keys_amount(MODULE_ID) == possible_deposits
    base_deposit_strategy.w3.lido.staking_router.get_staking_module_max_deposits_count.assert_called_once_with(
        MODULE_ID,
        depositable_eth,
    )
