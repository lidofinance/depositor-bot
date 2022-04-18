import json

import pytest
from brownie.network import web3, accounts

from scripts.utils import healthcheck_pulse
from tests.fixtures.depositor_fixtures import (
    DEPOSITOR_BASE_FIXTURES, DEPOSITOR_FIXTURES_WITH_HIGH_GAS,
    DEPOSITOR_FIXTURES_WITH_DEPOSIT_PROHIBIT, DEPOSITOR_FIXTURES_NOT_ENOUGH_BUFFERED_ETHER,
    DEPOSITOR_BASE_FIXTURES_SMALL_BALANCE, DEPOSITOR_FIXTURES_NO_FREE_KEYS,
)
from tests.fixtures.gas_fee_fixtures import GAS_FEE_FIXTURES
from tests.fixtures.pause_bot_fixtures import PAUSE_BOT_FIXTURES, PAUSED_PROTOCOL_FIXTURES
from tests.utils.mock_provider import MockProvider


class Message:
    def __init__(self, result):
        self._result = result

    def value(self):
        return self._result

    def error(self):
        pass


def send_message_to_kafka(monkeypatch, msgs):
    def make_poll():
        messages = msgs

        def _(instance=None, timeout=None):
            if messages:
                return Message(json.dumps(messages.pop()))

        return _

    from scripts.utils.kafka import Consumer
    monkeypatch.setattr(Consumer, 'poll', make_poll())


@pytest.fixture()
def setup_deposit_message_to_kafka(monkeypatch):
    send_message_to_kafka(monkeypatch, [{
        "type": "deposit",
        "depositRoot": "0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e",
        "keysOpIndex": 67,
        "blockNumber": 13726495,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
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


@pytest.fixture()
def setup_deposit_messages_to_kafka(monkeypatch):
    send_message_to_kafka(monkeypatch, [{
        "type": "deposit",
        "depositRoot": "0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e",
        "keysOpIndex": 67,
        "blockNumber": 13726495,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
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
    }, {
        "type": "deposit",
        "depositRoot": "0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e",
        "keysOpIndex": 67,
        "blockNumber": 13726495,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x33464Fe06c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
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
    }, {
        "type": "deposit",
        "depositRoot": "0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e",
        "keysOpIndex": 67,
        "blockNumber": 13726495,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x33464fE16c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
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
    }, {
        "type": "deposit",
        "depositRoot": "0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e",
        "keysOpIndex": 67,
        "blockNumber": 13726485,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x33464fE16c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
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


@pytest.fixture()
def setup_pause_message_to_kafka(monkeypatch):
    send_message_to_kafka(monkeypatch, [{
        "blockHash": "0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c",
        "blockNumber": 13726495,
        "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
        "guardianIndex": 0,
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
    send_message_to_kafka(monkeypatch, [{
        "type": "ping",
        "blockNumber": 13726495,
        "guardianIndex": 0,
        "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
        "app": {
            "version": "1.1.1",
            "name": "lido-council-daemon"
        }
    }])


@pytest.fixture(scope='function')
def setup_account(monkeypatch):
    from scripts.utils import variables

    monkeypatch.setenv('WALLET_PRIVATE_KEY', '0000000000000000000000000000000000000000000000000000000000000000')
    monkeypatch.setattr(variables, 'WALLET_PRIVATE_KEY', '0000000000000000000000000000000000000000000000000000000000000000')
    monkeypatch.setattr(variables, 'ACCOUNT', accounts.add(variables.WALLET_PRIVATE_KEY))
    yield
    monkeypatch.setenv('WALLET_PRIVATE_KEY', '')
    monkeypatch.setattr(variables, 'WALLET_PRIVATE_KEY', None)
    monkeypatch.setattr(variables, 'ACCOUNT', None)


@pytest.fixture(scope='function')
def setup_create_txs(monkeypatch):
    from scripts.utils import variables
    monkeypatch.setenv('CREATE_TRANSACTIONS', 'true')
    monkeypatch.setattr(variables, 'CREATE_TRANSACTIONS', True)
    yield
    monkeypatch.setenv('CREATE_TRANSACTIONS', 'false')
    monkeypatch.setattr(variables, 'CREATE_TRANSACTIONS', False)


@pytest.fixture(scope='function')
def setup_web3_fixtures_for_pause():
    web3.disconnect()
    web3.provider = MockProvider(PAUSE_BOT_FIXTURES)


@pytest.fixture(scope='function')
def setup_web3_fixtures_paused():
    web3.disconnect()
    web3.provider = MockProvider(PAUSED_PROTOCOL_FIXTURES)


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
def setup_web3_deposit_fixtures_prohibits_the_deposit():
    web3.disconnect()
    web3.provider = MockProvider(DEPOSITOR_FIXTURES_WITH_DEPOSIT_PROHIBIT)


@pytest.fixture()
def setup_web3_deposit_fixtures_not_enough_buffered_ether():
    web3.disconnect()
    web3.provider = MockProvider(DEPOSITOR_FIXTURES_NOT_ENOUGH_BUFFERED_ETHER)


@pytest.fixture()
def setup_web3_deposit_fixtures_no_free_keys():
    web3.disconnect()
    web3.provider = MockProvider(DEPOSITOR_FIXTURES_NO_FREE_KEYS)


@pytest.fixture()
def setup_web3_deposit_fixtures_with_high_gas():
    web3.disconnect()
    web3.provider = MockProvider(DEPOSITOR_FIXTURES_WITH_HIGH_GAS)


@pytest.fixture()
def pause_bot():
    from scripts.pauser_utils.pause_bot import DepositPauseBot

    bot = DepositPauseBot()
    yield bot
    del bot


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

    monkeypatch.setattr(healthcheck_pulse, 'pulse', lambda: None)
