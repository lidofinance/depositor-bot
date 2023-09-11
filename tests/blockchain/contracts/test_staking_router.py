import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


@pytest.mark.integration
def test_staking_router_call(staking_router, caplog):
    check_contract(
        staking_router,
        [
            ('get_staking_module_ids', None, lambda response: check_value_type(response, list) and
                                                              [check_value_type(x, int) for x in response]),
            ('is_staking_module_active', (1,), lambda response: check_value_type(response, bool)),
            ('is_staking_module_deposits_paused', (1,), lambda response: check_value_type(response, bool)),
            ('get_staking_module_nonce', (1,), lambda response: check_value_type(response, int)),
            ('get_staking_module_deposits_count', (1, 100*10**18), lambda response: check_value_type(response, int)),
        ],
        caplog,
    )
