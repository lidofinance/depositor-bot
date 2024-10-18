from unittest.mock import Mock

import pytest
import variables

MODULE_ID = 1


@pytest.mark.unit
def test_is_gas_price_ok(gas_price_calculator):
    gas_price_calculator.get_pending_base_fee = Mock(return_value=10)
    gas_price_calculator.get_recommended_gas_fee = Mock(return_value=20)
    variables.MAX_GAS_FEE = 300

    gas_price_calculator.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    variables.MAX_BUFFERED_ETHERS = 200
    assert gas_price_calculator.is_gas_price_ok(MODULE_ID)

    gas_price_calculator.get_recommended_gas_fee = Mock(return_value=5)
    assert not gas_price_calculator.is_gas_price_ok(MODULE_ID)

    gas_price_calculator.w3.lido.lido.get_depositable_ether = Mock(return_value=300)
    assert gas_price_calculator.is_gas_price_ok(MODULE_ID)

    gas_price_calculator.get_pending_base_fee = Mock(return_value=400)
    assert not gas_price_calculator.is_gas_price_ok(MODULE_ID)


@pytest.mark.unit
@pytest.mark.parametrize(
    'deposits,expected_range',
    [(1, (0, 20)), (5, (20, 100)), (10, (50, 1000)), (100, (1000, 1000000))],
)
def test_calculate_recommended_gas_based_on_deposit_amount(gas_price_calculator, deposits, expected_range):
    assert (
        expected_range[0] * 10**9
        <= gas_price_calculator._calculate_recommended_gas_based_on_deposit_amount(deposits, MODULE_ID)
        <= expected_range[1] * 10**9
    )


@pytest.mark.unit
def test_get_recommended_gas_fee(gas_price_calculator):
    gas_price_calculator._fetch_gas_fee_history = Mock(return_value=list(range(11)))
    variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1 = 1
    variables.GAS_FEE_PERCENTILE_1 = 50

    assert gas_price_calculator.get_recommended_gas_fee() == 5

    variables.GAS_FEE_PERCENTILE_1 = 30
    assert gas_price_calculator.get_recommended_gas_fee() == 3


@pytest.mark.integration
def test_get_pending_base_fee(gas_price_calculator_integration):
    pending_gas = gas_price_calculator_integration.get_pending_base_fee()
    assert 1 <= pending_gas <= 1000 * 10**9


@pytest.mark.integration
def test_fetch_gas_fee_history(gas_price_calculator_integration):
    history = gas_price_calculator_integration._fetch_gas_fee_history(1)
    assert isinstance(history, list)
    assert len(history) == 1 * 24 * 60 * 60 / 12
