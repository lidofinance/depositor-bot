import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_re, HASH_REGREX, check_value_type


@pytest.mark.integration
def test_staking_module_contract_call(staking_module, caplog):
    check_contract(
        staking_module,
        [
            ('get_staking_module_id', None, lambda response: check_value_type(response, int)),
            ('weth', None, lambda response: check_value_re(HASH_REGREX, '0x' + response.hex())),
        ],
        caplog,
    )
