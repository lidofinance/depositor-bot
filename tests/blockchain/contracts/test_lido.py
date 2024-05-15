from tests.utils.contract_utils import check_contract
from tests.utils.regrex import check_value_type


def test_lido_contract_call(lido_contract, caplog):
	check_contract(
		lido_contract,
		[
			('get_depositable_ether', None, lambda response: check_value_type(response, int)),
		],
		caplog,
	)
