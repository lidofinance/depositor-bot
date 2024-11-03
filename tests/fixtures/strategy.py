import pytest
from blockchain.deposit_strategy.base_deposit_strategy import CSMDepositStrategy, DefaultDepositStrategy
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator


@pytest.fixture
def base_deposit_strategy(w3_unit, gas_price_calculator):
    yield DefaultDepositStrategy(w3_unit, gas_price_calculator)


@pytest.fixture
def base_deposit_strategy_integration(web3_lido_integration, gas_price_calculator_integration):
    yield DefaultDepositStrategy(web3_lido_integration, gas_price_calculator_integration)


@pytest.fixture
def deposit_transaction_sender(w3_unit) -> Sender:
    yield Sender(w3_unit)


@pytest.fixture
def deposit_transaction_sender_integration(web3_lido_integration) -> Sender:
    yield Sender(web3_lido_integration)


@pytest.fixture
def gas_price_calculator(w3_unit):
    yield GasPriceCalculator(w3_unit)


@pytest.fixture
def gas_price_calculator_integration(web3_lido_integration):
    yield GasPriceCalculator(web3_lido_integration)


@pytest.fixture
def csm_strategy(w3_unit, gas_price_calculator):
    yield CSMDepositStrategy(w3_unit, gas_price_calculator)


@pytest.fixture
def csm_strategy_integration(web3_lido_integration, gas_price_calculator_integration):
    yield CSMDepositStrategy(web3_lido_integration, gas_price_calculator_integration)
