from unittest.mock import Mock

import pytest

from blockchain.deposit_strategy.prefered_module_to_deposit import (
    get_preferred_to_deposit_modules,
    get_module_depositable_filter,
    prioritize_modules,
)


@pytest.mark.unit
def test_get_preferred_to_deposit_module(web3_lido_unit):
    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1,2,3,4])
    web3_lido_unit.lido.staking_router.get_staking_module_digests = Mock(return_value=[
        (0, 0, (1,), (10, 20, 10)),
        (0, 0, (2,), (0, 10, 10,)),
        (0, 0, (3,), (3000, 4000, 10,)),
        (0, 0, (6,), (5, 10, 10,)),
        (0, 0, (12,), (3000, 4000, 10,)),
    ])
    web3_lido_unit.lido.staking_router.is_staking_module_active = lambda x: not x % 2
    web3_lido_unit.lido.deposit_security_module.can_deposit = lambda x: not x % 2

    result = get_preferred_to_deposit_modules(web3_lido_unit, [1,2,3,6])

    assert result == [6, 2]


@pytest.mark.unit
def test_prioritize_modules(web3_lido_unit):
    order = prioritize_modules([
        (0, 0, (0,), (10, 20, 10)),
        (0, 0, (1,), (5, 10, 10,)),
        (0, 0, (2,), (3000, 4000, 10,)),
    ])

    assert order == [1, 0, 2]


@pytest.mark.unit
def test_get_module_filter(web3_lido_unit):
    web3_lido_unit.lido.staking_router.is_staking_module_active = lambda x: not x % 2
    web3_lido_unit.lido.deposit_security_module.can_deposit = lambda x: not x % 3

    module_filter = get_module_depositable_filter(web3_lido_unit, [0,1,2,3,4,5,6])
    available_modules = list(filter(module_filter, [
        (0, 0, (0,), (0,)),
        (0, 0, (1,), (0,)),
        (0, 0, (2,), (0,)),
        (0, 0, (3,), (0,)),
        (0, 0, (4,), (0,)),
        (0, 0, (5,), (0,)),
        (0, 0, (6,), (0,)),
        (0, 0, (12,), (0,)),
    ]))

    assert available_modules == [(0, 0, (0,), (0,)), (0, 0, (6,), (0,))]
