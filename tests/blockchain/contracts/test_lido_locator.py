from tests.utils.contract_utils import check_contract
from tests.utils.regrex import ADDRESS_REGREX, check_value_re


def test_lido_locator_call(lido_locator, caplog):
	check_contract(
		lido_locator,
		[
			('lido', None, lambda response: check_value_re(ADDRESS_REGREX, response)),
			('deposit_security_module', None, lambda response: check_value_re(ADDRESS_REGREX, response)),
			('staking_router', None, lambda response: check_value_re(ADDRESS_REGREX, response)),
		],
		caplog,
	)
