import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import HASH_REGREX, check_value_re


@pytest.mark.integration
def test_deposit_contract_call(deposit_contract, caplog):
    check_contract(
        deposit_contract,
        [
            ('get_deposit_root', None, lambda response: check_value_re(HASH_REGREX, '0x' + response.hex())),
        ],
        caplog,
    )
