import json
from unittest.mock import Mock

import pytest
from eth_account import Account
from web3 import Web3

from fixtures.depositor_fixtures import (
    DEPOSITOR_BASE_FIXTURES_SMALL_BALANCE,
    DEPOSITOR_FIXTURES_WITH_DEPOSIT_PROHIBIT,
    DEPOSITOR_FIXTURES_WITH_HIGH_GAS,
    DEPOSITOR_FIXTURES_NOT_ENOUGH_BUFFERED_ETHER,
    DEPOSITOR_BASE_FIXTURES, DEPOSITOR_FIXTURES_NO_FREE_KEYS,
)
from fixtures.pause_bot_fixtures import PAUSE_BOT_FIXTURES, PAUSED_PROTOCOL_FIXTURES
from metrics import healthcheck_pulse
from tests_old.utils.mock_provider import MockProvider

from tests_old.fixtures.gas_fee_fixtures import GAS_FEE_FIXTURES
from transport.msg_providers.kafka import KafkaMessageProvider
from transport.msg_providers.rabbit import RabbitProvider
from transport.msg_storage import MessageStorage


class Message:
    def __init__(self, result):
        self._result = result

    def value(self):
        return self._result

    def error(self):
        pass


def send_message_to_store(monkeypatch, msgs):
    monkeypatch.setattr(MessageStorage, 'messages', msgs)


@pytest.fixture(scope='function')
def web3_gas_fee():
    return Web3(MockProvider(GAS_FEE_FIXTURES))


@pytest.fixture(scope='function')
def setup_web3_fixtures_for_pause():
    return Web3(MockProvider(PAUSE_BOT_FIXTURES))


@pytest.fixture(scope='function')
def setup_web3_fixtures_paused():
    return Web3(MockProvider(PAUSED_PROTOCOL_FIXTURES))


@pytest.fixture()
def setup_web3_deposit_fixtures_small_balance():
    return Web3(MockProvider(DEPOSITOR_BASE_FIXTURES_SMALL_BALANCE))


@pytest.fixture()
def setup_web3_deposit_fixtures_prohibits_the_deposit():
    return Web3(MockProvider(DEPOSITOR_FIXTURES_WITH_DEPOSIT_PROHIBIT))


@pytest.fixture()
def setup_web3_deposit_fixtures_with_high_gas():
    return Web3(MockProvider(DEPOSITOR_FIXTURES_WITH_HIGH_GAS))


@pytest.fixture()
def setup_web3_deposit_fixtures_not_enough_buffered_ether():
    return Web3(MockProvider(DEPOSITOR_FIXTURES_NOT_ENOUGH_BUFFERED_ETHER))


@pytest.fixture()
def setup_web3_deposit_fixtures():
    return Web3(MockProvider(DEPOSITOR_BASE_FIXTURES))


@pytest.fixture()
def setup_web3_deposit_fixtures_no_free_keys():
    return Web3(MockProvider(DEPOSITOR_FIXTURES_NO_FREE_KEYS))


@pytest.fixture()
def setup_pause_message_to_kafka(monkeypatch):
    send_message_to_store(monkeypatch, [{
        "blockHash": "0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c",
        "blockNumber": 13726495,
        "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
        "guardianIndex": 0,
        "stakingModuleId": 1,
        "signature": {
            "_vs": "0xd4933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
            "r": "0xbaa668505cd496caaf7117dd074338197200175057909ab73a04463656bdb0fa",
            "recoveryParam": 1,
            "s": "0x54933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
            "v": 28
        },
        "type": "pause"
    }])


@pytest.fixture()
def setup_ping_message_to_kafka(monkeypatch):
    send_message_to_store(monkeypatch, [{
        "type": "ping",
        "blockNumber": 13726495,
        "guardianIndex": 0,
        "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
        "app": {
            "version": "1.1.1",
            "name": "lido-council-daemon"
        }
    }])


@pytest.fixture()
def remove_sleep(monkeypatch):
    import time
    monkeypatch.setattr(time, 'sleep', lambda x: x)

    monkeypatch.setattr(healthcheck_pulse, 'pulse', lambda: None)


@pytest.fixture()
def remove_transport(monkeypatch):
    monkeypatch.setattr(KafkaMessageProvider, '__init__', lambda _, client, message_schema: None)
    monkeypatch.setattr(KafkaMessageProvider, '_receive_message', lambda _: None)
    monkeypatch.setattr(KafkaMessageProvider, '__del__', lambda _: None)

    monkeypatch.setattr(RabbitProvider, '__init__', lambda _, client, message_schema, routing_keys: None)
    monkeypatch.setattr(RabbitProvider, '_receive_message', lambda _: None)
    monkeypatch.setattr(RabbitProvider, '__del__', lambda _: None)


@pytest.fixture()
def setup_pause_message_to_store(monkeypatch):
    send_message_to_store(monkeypatch, [{
        "blockHash": "0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c",
        "blockNumber": 13726495,
        "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
        "guardianIndex": 0,
        "stakingModuleId": 1,
        "signature": {
            "_vs": "0xd4933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
            "r": "0xbaa668505cd496caaf7117dd074338197200175057909ab73a04463656bdb0fa",
            "recoveryParam": 1,
            "s": "0x54933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
            "v": 28
        },
        "type": "pause"
    }])


@pytest.fixture(scope='function')
def setup_account(monkeypatch):
    import variables

    monkeypatch.setenv('WALLET_PRIVATE_KEY', '0000000000000000000000000000000000000000000000000000000000000000')
    monkeypatch.setattr(variables, 'WALLET_PRIVATE_KEY', '0000000000000000000000000000000000000000000000000000000000000000')
    monkeypatch.setattr(variables, 'ACCOUNT', Account.from_key(variables.WALLET_PRIVATE_KEY))
    yield
    monkeypatch.setenv('WALLET_PRIVATE_KEY', '')
    monkeypatch.setattr(variables, 'WALLET_PRIVATE_KEY', None)
    monkeypatch.setattr(variables, 'ACCOUNT', None)


@pytest.fixture
def setup_flashbots(monkeypatch):
    import variables
    monkeypatch.setattr(variables, 'FLASHBOT_SIGNATURE', '0000000000000000000000000000000000000000000000000000000000000000')
    yield
    monkeypatch.setattr(variables, 'FLASHBOT_SIGNATURE', None)


@pytest.fixture(scope='function')
def setup_create_txs(monkeypatch):
    import variables
    monkeypatch.setenv('CREATE_TRANSACTIONS', 'true')
    monkeypatch.setattr(variables, 'CREATE_TRANSACTIONS', True)
    yield
    monkeypatch.setenv('CREATE_TRANSACTIONS', 'false')
    monkeypatch.setattr(variables, 'CREATE_TRANSACTIONS', False)


@pytest.fixture()
def setup_deposit_message_to_kafka(monkeypatch):
    send_message_to_store(monkeypatch, [{
        "type": "deposit",
        "depositRoot": "0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e",
        "nonce": 1,
        "blockNumber": 13726495,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
        "stakingModuleId": 1,
        "signature": {
            "r": "0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116",
            "s": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "_vs": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "recoveryParam": 0,
            "v": 27
        },
        "app": {
            "version": "1.0.3",
            "name": "lido-council-daemon"
        }
    }])

