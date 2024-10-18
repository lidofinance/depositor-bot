from unittest.mock import Mock

import pytest


@pytest.mark.unit
def test_csm_deposit_strategy(csm_strategy):
    csm_strategy.deposited_keys_amount = Mock(return_value=1)
    assert not csm_strategy.can_deposit_keys_based_on_ether(3)

    csm_strategy.deposited_keys_amount = Mock(return_value=2)
    csm_strategy._gas_price_calculator.get_pending_base_fee = Mock(return_value=10)
    assert csm_strategy.can_deposit_keys_based_on_ether(3)
