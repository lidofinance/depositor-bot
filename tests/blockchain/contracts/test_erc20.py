import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


@pytest.mark.holesky
def test_erc20(erc20, simple_dvt_staking_strategy, caplog):
    check_contract(
        erc20,
        [
            ('balance_of', (simple_dvt_staking_strategy.vault(),), lambda response: check_value_type(response, int)),
        ],
        caplog,
    )
