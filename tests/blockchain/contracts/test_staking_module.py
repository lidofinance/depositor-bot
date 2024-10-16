import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import ADDRESS_REGREX, check_value_re, check_value_type


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': 'https://ethereum-holesky-rpc.publicnode.com'}],
    indirect=['web3_provider_integration'],
)
def test_staking_module_contract_call(staking_module, caplog):
    check_contract(
        staking_module,
        [
            ('get_staking_module_id', None, lambda response: check_value_type(response, int)),
            ('weth', None, lambda response: check_value_re(ADDRESS_REGREX, response)),
        ],
        caplog,
    )
