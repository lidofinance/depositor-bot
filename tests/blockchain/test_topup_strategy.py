from unittest.mock import Mock, patch

import pytest

import variables
from blockchain.topup.cmv2_strategy import CMv2TopUpStrategy


@pytest.fixture
def topup_strategy():
    w3 = Mock()
    w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    gas_price_calculator = Mock()
    gas_price_calculator.get_pending_base_fee = Mock(return_value=10)
    gas_price_calculator.get_recommended_gas_fee = Mock(return_value=20)
    return CMv2TopUpStrategy(w3, gas_price_calculator)


@pytest.mark.unit
def test_is_gas_price_ok_reports_current_and_recommended_fee(topup_strategy):
    """Gas fee values used for the check must be observable — otherwise TOPUP_GAS_OK's boolean
    can't be explained without re-deriving the inputs from logs."""
    # Save and restore the globals this test mutates, otherwise the leaked values break later tests
    # (e.g. the integration deposit test reads MAX_GAS_FEE / MAX_BUFFERED_ETHERS and would reject deposits).
    saved_max_buffered = variables.MAX_BUFFERED_ETHERS
    try:
        variables.MAX_BUFFERED_ETHERS = 200  # buffered (100) below threshold -> recommended-fee branch

        with patch('blockchain.topup.strategy.TOPUP_GAS_FEE') as topup_gas_fee:
            assert topup_strategy.is_gas_price_ok()

        topup_gas_fee.labels.assert_any_call('current_fee')
        topup_gas_fee.labels.assert_any_call('recommended_fee')
        topup_gas_fee.labels.return_value.set.assert_any_call(10)
        topup_gas_fee.labels.return_value.set.assert_any_call(20)
    finally:
        variables.MAX_BUFFERED_ETHERS = saved_max_buffered


@pytest.mark.unit
def test_is_gas_price_ok_uses_max_gas_fee_above_buffer_threshold(topup_strategy):
    saved_max_gas_fee = variables.MAX_GAS_FEE
    saved_max_buffered = variables.MAX_BUFFERED_ETHERS
    try:
        variables.MAX_BUFFERED_ETHERS = 50  # buffered (100) above threshold -> max-fee branch
        variables.MAX_GAS_FEE = 5

        with patch('blockchain.topup.strategy.TOPUP_GAS_FEE'):
            assert not topup_strategy.is_gas_price_ok()  # current_fee (10) > MAX_GAS_FEE (5)
    finally:
        variables.MAX_GAS_FEE = saved_max_gas_fee
        variables.MAX_BUFFERED_ETHERS = saved_max_buffered
