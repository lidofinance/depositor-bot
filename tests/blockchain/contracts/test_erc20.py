import pytest
import variables

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': variables.TESTNET_WEB3_RPC_ENDPOINTS[0]}],
    indirect=['web3_provider_integration'],
)
def test_erc20(weth, simple_dvt_staking_strategy, caplog):
    check_contract(
        weth,
        [
            ('balance_of', (simple_dvt_staking_strategy.vault(),), lambda response: check_value_type(response, int)),
        ],
        caplog,
    )
