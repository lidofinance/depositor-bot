import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'block': 3247161}],  # hoodi block with a curated-onchain-v2 (CMV2) module
    indirect=['web3_provider_integration'],
)
def test_cmv2_call(web3_provider_integration, cmv2_contract, caplog):
    check_contract(
        cmv2_contract,
        [
            (
                'get_deposits_allocation',
                (32 * 10**18,),
                lambda response: (
                    check_value_type(response, list)
                    and len(response) == 3
                    and check_value_type(response[0], int)
                    and check_value_type(response[1], list)
                    and check_value_type(response[2], list)
                ),
            ),
        ],
        caplog,
    )
