import json

import pytest
from brownie.network import web3, accounts

from tests.fixtures.depositor_fixtures import (
    DEPOSITOR_BASE_FIXTURES, DEPOSITOR_FIXTURES_WITH_HIGH_GAS,
    DELEGATOR_FIXTURES_NOT_ENOUGH_REWARDS, DELEGATOR_FIXTURES_NOT_ENOUGH_BUFFERED_MATIC,
    DEPOSITOR_BASE_FIXTURES_SMALL_BALANCE, DISTRIBUTE_BASE_REWARDS_FIXTURES, DELEGATE_BASE_FIXTURES,
    DELEGATE_FIXTURES_IN_RANGE, DELEGATE_FIXTURES_OUT_RANGE
)
from tests.fixtures.gas_fee_fixtures import GAS_FEE_FIXTURES
from tests.utils.mock_provider import MockProvider


class Message:
    def __init__(self, result):
        self._result = result

    def value(self):
        return self._result

    def error(self):
        pass


@pytest.fixture(scope='function')
def setup_no_account(monkeypatch):
    from scripts.utils import variables
    monkeypatch.setenv('WALLET_PRIVATE_KEY', '')
    monkeypatch.setattr(variables, 'WALLET_PRIVATE_KEY', None)
    monkeypatch.setattr(variables, 'ACCOUNT', None)


@pytest.fixture(scope='function')
def setup_account(monkeypatch):
    from scripts.utils import variables

    monkeypatch.setenv('WALLET_PRIVATE_KEY',
                       '0000000000000000000000000000000000000000000000000000000000000000')
    monkeypatch.setattr(variables, 'WALLET_PRIVATE_KEY',
                        '0000000000000000000000000000000000000000000000000000000000000000')
    monkeypatch.setattr(variables, 'ACCOUNT', accounts.add(
        variables.WALLET_PRIVATE_KEY))


@pytest.fixture(scope='function')
def setup_create_txs(monkeypatch):
    from scripts.utils import variables
    monkeypatch.setenv('CREATE_TRANSACTIONS', 'true')
    monkeypatch.setattr(variables, 'CREATE_TRANSACTIONS', True)
    yield
    monkeypatch.setenv('CREATE_TRANSACTIONS', 'false')
    monkeypatch.setattr(variables, 'CREATE_TRANSACTIONS', False)

@pytest.fixture(scope='function')
def setup_no_create_txs(monkeypatch):
    from scripts.utils import variables
    monkeypatch.setenv('CREATE_TRANSACTIONS', 'false')
    monkeypatch.setattr(variables, 'CREATE_TRANSACTIONS', False)

@pytest.fixture(scope='function')
def setup_web3_fixtures_distribute_rewards():
    web3.disconnect()
    web3.provider = MockProvider(DISTRIBUTE_BASE_REWARDS_FIXTURES)


@pytest.fixture(scope='function')
def setup_web3_fixtures_delegate():
    web3.disconnect()
    web3.provider = MockProvider(DELEGATE_BASE_FIXTURES)

@pytest.fixture(scope='function')
def setup_web3_fixtures_delegate_in_range():
    web3.disconnect()
    web3.provider = MockProvider(DELEGATE_FIXTURES_IN_RANGE)

@pytest.fixture(scope='function')
def setup_web3_fixtures_delegate_out_range():
    web3.disconnect()
    web3.provider = MockProvider(DELEGATE_FIXTURES_OUT_RANGE)

@pytest.fixture(scope='function')
def setup_web3_gas_fee_fixtures():
    web3.disconnect()
    web3.provider = MockProvider(GAS_FEE_FIXTURES)


@pytest.fixture()
def setup_web3_deposit_fixtures():
    web3.disconnect()
    web3.provider = MockProvider(DEPOSITOR_BASE_FIXTURES)


@pytest.fixture()
def setup_web3_deposit_fixtures_small_balance():
    web3.disconnect()
    web3.provider = MockProvider(DEPOSITOR_BASE_FIXTURES_SMALL_BALANCE)


@pytest.fixture()
def setup_web3_deposit_fixtures_not_enough_buffered_matic():
    web3.disconnect()
    web3.provider = MockProvider(DELEGATOR_FIXTURES_NOT_ENOUGH_BUFFERED_MATIC)


@pytest.fixture()
def setup_web3_deposit_fixtures_not_enough_rewards():
    web3.disconnect()
    web3.provider = MockProvider(DELEGATOR_FIXTURES_NOT_ENOUGH_REWARDS)


@pytest.fixture()
def setup_web3_deposit_fixtures_with_high_gas():
    web3.disconnect()
    web3.provider = MockProvider(DEPOSITOR_FIXTURES_WITH_HIGH_GAS)


@pytest.fixture()
def depositor_bot():
    from scripts.depositor_utils.depositor_bot import DepositorBot

    bot = DepositorBot()
    yield bot
    del bot


@pytest.fixture()
def remove_sleep(monkeypatch):
    import time
    monkeypatch.setattr(time, 'sleep', lambda x: x)
