import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_re, ADDRESS_REGREX


@pytest.mark.integration_holesky
def test_simple_dvt_staking_strategy_contract_call(simple_dvt_staking_strategy, caplog):
    check_contract(
        simple_dvt_staking_strategy,
        [
            ('get_staking_module', None, lambda response: check_value_re(ADDRESS_REGREX, response)),
            ('vault', None, lambda response: check_value_re(ADDRESS_REGREX, response)),
        ],
        caplog,
    )
