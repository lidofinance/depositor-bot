import pytest

from tests.fixtures import deposit_security_module_v2
from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_re, check_value_type, ADDRESS_REGREX


@pytest.mark.integration
def test_deposit_security_module_call(deposit_security_module, caplog):
    check_contract(
        deposit_security_module,
        [
            ('get_guardian_quorum', None, lambda response: check_value_type(response, int)),
            ('get_guardians', None, lambda response: check_value_type(response, list) and
                                                        [check_value_re(ADDRESS_REGREX, g) for g in response]),
            ('get_attest_message_prefix', None, lambda response: check_value_type(response, bytes)),
            ('can_deposit', (1,), lambda response: check_value_type(response, bool)),
            ('get_pause_message_prefix', None, lambda response: check_value_type(response, bytes)),
            ('get_pause_intent_validity_period_blocks', None, lambda response: check_value_type(response, int)),
        ],
        caplog,
    )


@pytest.mark.integration
def test_deposit_security_module_v2_call(caplog, deposit_security_module_v2):
    check_contract(
        deposit_security_module_v2,
        [
            # ToDo uncomment after upgrade
            # ('get_guardian_quorum', None, lambda response: check_value_type(response, int)),
            # ('get_guardians', None, lambda response: check_value_type(response, list) and
            #                                             [check_value_re(ADDRESS_REGREX, g) for g in response]),
            # ('get_attest_message_prefix', None, lambda response: check_value_type(response, bytes)),
            # ('can_deposit', (1,), lambda response: check_value_type(response, bool)),
            # ('get_pause_message_prefix', None, lambda response: check_value_type(response, bytes)),
            # ('get_pause_intent_validity_period_blocks', None, lambda response: check_value_type(response, int)),
            ('is_deposits_paused', None, lambda response: check_value_type(response, bool))
        ],
        caplog,
    )
