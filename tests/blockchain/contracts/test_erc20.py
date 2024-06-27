import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


@pytest.mark.holesky
def test_erc20(weth, simple_dvt_staking_strategy, caplog):
    check_contract(
        weth,
        [
            ('balance_of', (simple_dvt_staking_strategy.vault(),), lambda response: check_value_type(response, int)),
        ],
        caplog,
    )
