import pytest
from blockchain.deposit_strategy.base_deposit_strategy import CSMDepositStrategy, DefaultDepositStrategy
from blockchain.deposit_strategy.deposit_module_recommender import DepositModuleRecommender
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator


@pytest.fixture
def base_deposit_strategy(web3_lido_unit, gas_price_calculator):
    yield DefaultDepositStrategy(web3_lido_unit, gas_price_calculator)


@pytest.fixture
def base_deposit_strategy_integration(web3_lido_integration, gas_price_calculator_integration):
    yield DefaultDepositStrategy(web3_lido_integration, gas_price_calculator_integration)


@pytest.fixture
def deposit_transaction_sender(web3_lido_unit) -> Sender:
    yield Sender(web3_lido_unit)


@pytest.fixture
def deposit_transaction_sender_integration(web3_lido_integration) -> Sender:
    yield Sender(web3_lido_integration)


@pytest.fixture
def gas_price_calculator(web3_lido_unit):
    yield GasPriceCalculator(web3_lido_unit)


@pytest.fixture
def gas_price_calculator_integration(web3_lido_integration):
    yield GasPriceCalculator(web3_lido_integration)


@pytest.fixture
def csm_strategy(web3_lido_unit, gas_price_calculator):
    yield CSMDepositStrategy(web3_lido_unit, gas_price_calculator)


@pytest.fixture
def csm_strategy_integration(web3_lido_integration, gas_price_calculator_integration):
    yield CSMDepositStrategy(web3_lido_integration, gas_price_calculator_integration)


@pytest.fixture
def module_recommender(web3_lido_unit):
    yield DepositModuleRecommender(web3_lido_unit)


@pytest.fixture
def module_recommender_integration(web3_lido_integration):
    yield DepositModuleRecommender(web3_lido_integration)
