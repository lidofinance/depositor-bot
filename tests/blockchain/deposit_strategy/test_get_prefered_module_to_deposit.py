from unittest.mock import Mock

import pytest

from blockchain.deposit_strategy.prefered_module_to_deposit import (
    get_active_modules,
    get_modules_stats,
    get_preferred_to_deposit_module,
)


@pytest.mark.unit
def test_get_preferred_to_deposit_module(web3_lido_unit):
    modules = list(range(10))

    web3_lido_unit.lido.deposit_security_module.get_max_deposits = Mock(return_value=100)
    web3_lido_unit.lido.lido.get_depositable_ether = Mock(return_value=10 * 32 * 10 ** 18)
    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=modules)
    web3_lido_unit.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=0)

    result = get_preferred_to_deposit_module(web3_lido_unit, modules[:-2])

    assert result == 7


def test_active_modules(web3_lido_unit):
    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1, 2, 3, 4, 5, 6])
    web3_lido_unit.lido.staking_router.is_staking_module_active = lambda x: x % 2

    modules_list = get_active_modules(web3_lido_unit, [1, 2, 3, 4])

    assert modules_list == [1, 3]


def test_get_module_stats(web3_lido_unit):
    web3_lido_unit.lido.deposit_security_module.get_max_deposits = Mock(return_value=100)
    web3_lido_unit.lido.lido.get_depositable_ether = Mock(return_value=10 * 32 * 10 ** 18)
    web3_lido_unit.lido.staking_router.get_staking_module_max_deposits_count = lambda x, y: x % 3

    stats = get_modules_stats(web3_lido_unit, modules=list(range(8)))

    for i in range(len(stats) - 1):
        assert stats[i][0] >= stats[i + 1][0]

        if stats[i][1] > stats[i + 1][1]:
            assert stats[i][2] <= stats[i - 1][2]
        elif stats[i][1] == stats[i + 1][1]:
            assert stats[i][0] == stats[i + 1][0]
