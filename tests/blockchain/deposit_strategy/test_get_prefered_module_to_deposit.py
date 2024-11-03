from unittest.mock import Mock

import pytest
from blockchain.deposit_strategy.deposit_order import get_preferred_to_deposit_modules_ids, get_prioritized_module_ids

from tests.factories.staking_module import StakingModuleDigestFactory


@pytest.mark.unit
@pytest.mark.parametrize(
    'deposited_validators, exited_validators, expected_order, white_list',
    [
        ([20, 25], [10, 1], [0, 1], [1, 0]),
        ([50, 40], [0, 40], [1, 0], [0]),
        ([30, 30, 50], [20, 0, 30], [0, 2, 1], [1, 0]),
        ([30, 20, 10], [0, 0, 0], [2, 1, 0], [5]),
    ],
)
def test_get_prioritized_module_ids(w3_unit, deposited_validators, exited_validators, expected_order, white_list):
    module_ids = list(range(len(deposited_validators)))
    staking_modules = StakingModuleDigestFactory.batch_with(
        state__id=module_ids,
        summary__total_deposited_validators=deposited_validators,
        summary__total_exited_validators=exited_validators,
    )

    w3_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=module_ids)
    w3_unit.lido.staking_router.get_staking_module_digests = Mock(return_value=staking_modules)

    assert get_prioritized_module_ids(staking_modules) == expected_order, 'Invalid priority order'

    assert [module_id for module_id in expected_order if module_id in white_list] == get_preferred_to_deposit_modules_ids(
        w3_unit, white_list
    ), 'Whitelist exception'
