import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


@pytest.mark.integration
def test_topup_gateway_call(topup_gateway, caplog):
    check_contract(
        topup_gateway,
        [
            ('is_paused', None, lambda response: check_value_type(response, bool)),
            ('is_block_distance_passed', None, lambda response: check_value_type(response, bool)),
            ('get_max_validators_per_top_up', None, lambda response: check_value_type(response, int)),
            ('get_target_balance_gwei', None, lambda response: check_value_type(response, int)),
            ('get_min_top_up_gwei', None, lambda response: check_value_type(response, int)),
        ],
        caplog,
    )
