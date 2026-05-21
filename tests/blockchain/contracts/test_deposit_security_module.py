import pytest

from tests.utils.contract_utils import check_contract
from tests.utils.regrex import ADDRESS_REGREX, check_value_re, check_value_type


@pytest.mark.integration
def test_deposit_security_module_call(caplog, deposit_security_module):
    check_contract(
        deposit_security_module,
        [
            ('get_guardian_quorum', None, lambda response: check_value_type(response, int)),
            (
                'get_guardians',
                None,
                lambda response: check_value_type(response, list) and [check_value_re(ADDRESS_REGREX, g) for g in response],
            ),
            ('get_attest_message_prefix', None, lambda response: check_value_type(response, bytes)),
            ('can_deposit', (1,), lambda response: check_value_type(response, bool)),
            ('get_pause_message_prefix', None, lambda response: check_value_type(response, bytes)),
            ('get_pause_intent_validity_period_blocks', None, lambda response: check_value_type(response, int)),
            ('is_deposits_paused', None, lambda response: check_value_type(response, bool)),
        ],
        caplog,
    )
