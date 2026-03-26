import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


@pytest.mark.integration
def test_staking_router_call_v3(staking_router_v3, caplog):
    check_contract(
        staking_router_v3,
        [
            (
                'get_staking_module_ids',
                None,
                lambda response: check_value_type(response, list) and [check_value_type(x, int) for x in response],
            ),
            ('is_staking_module_active', (1,), lambda response: check_value_type(response, bool)),
            ('get_staking_module_digests', ([1],), lambda response: check_value_type(response, list)),
            ('get_staking_module_nonce', (1,), lambda response: check_value_type(response, int)),
            ('get_staking_module_max_deposits_count', (1, 100 * 10**18), lambda response: check_value_type(response, int)),
        ],
        caplog,
    )


@pytest.mark.integration
def test_staking_router_call_v4(staking_router_v4, caplog):
    if staking_router_v4.get_contract_version() != 4:
        pytest.skip('StakingRouter V4 is not deployed on the current RPC target.')

    check_contract(
        staking_router_v4,
        [
            (
                'get_staking_module_ids',
                None,
                lambda response: check_value_type(response, list) and [check_value_type(x, int) for x in response],
            ),
            ('is_staking_module_active', (1,), lambda response: check_value_type(response, bool)),
            ('get_staking_module_digests', ([1],), lambda response: check_value_type(response, list)),
            ('get_staking_module_nonce', (1,), lambda response: check_value_type(response, int)),
            ('get_staking_module_max_deposits_count', (1, 100 * 10**18), lambda response: check_value_type(response, int)),
            (
                'get_deposit_allocations',
                (32 * 10**18, False),
                lambda response: check_value_type(response, tuple) and len(response) == 3,
            ),
        ],
        caplog,
    )
