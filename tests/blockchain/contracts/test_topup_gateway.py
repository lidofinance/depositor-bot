import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


@pytest.mark.integration
def test_topup_gateway_call(topup_gateway, caplog):
    check_contract(
        topup_gateway,
        [
            ('can_top_up', (1,), lambda response: check_value_type(response, bool)),
            ('get_max_validators_per_top_up', None, lambda response: check_value_type(response, int)),
        ],
        caplog,
    )
