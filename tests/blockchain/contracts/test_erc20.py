import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import HASH_REGREX, check_value_re


@pytest.mark.integration
def test_erc20(erc20, caplog):
    check_contract(
        erc20,
        [
            ('balance_of', (1,), lambda response: check_value_re(HASH_REGREX, '0x' + response.hex())),
        ],
        caplog,
    )
