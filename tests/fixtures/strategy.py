import pytest
from blockchain.deposit_strategy.base_deposit_strategy import BaseDepositStrategy, MellowDepositStrategy
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator


@pytest.fixture
def base_deposit_strategy(web3_lido_unit):
    yield BaseDepositStrategy(web3_lido_unit)


@pytest.fixture
def mellow_deposit_strategy(web3_lido_unit):
    yield MellowDepositStrategy(web3_lido_unit)


@pytest.fixture
def deposit_transaction_sender(web3_lido_unit):
    yield Sender(web3_lido_unit)


@pytest.fixture
def deposit_transaction_sender_integration(web3_lido_integration):
    yield Sender(web3_lido_integration)


@pytest.fixture
def gas_price_calculator(web3_lido_unit):
    yield GasPriceCalculator(web3_lido_unit)


@pytest.fixture
def gas_price_calculator_integration(web3_lido_integration):
    yield GasPriceCalculator(web3_lido_integration)
