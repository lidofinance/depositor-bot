import pytest
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator


@pytest.fixture
def gas_price_calculator(web3_lido_unit):
    yield GasPriceCalculator(web3_lido_unit)
