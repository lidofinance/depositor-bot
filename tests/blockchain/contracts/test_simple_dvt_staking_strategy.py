import pytest
import variables

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import ADDRESS_REGREX, check_value_re


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': variables.TESTNET_WEB3_RPC_ENDPOINTS[0]}],
    indirect=['web3_provider_integration'],
)
def test_simple_dvt_staking_strategy_contract_call(simple_dvt_staking_strategy, caplog):
    check_contract(
        simple_dvt_staking_strategy,
        [
            ('get_staking_module', None, lambda response: check_value_re(ADDRESS_REGREX, response)),
            ('vault', None, lambda response: check_value_re(ADDRESS_REGREX, response)),
        ],
        caplog,
    )
