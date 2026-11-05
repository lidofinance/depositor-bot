from unittest.mock import Mock

import pytest

from bots.pauser import PauserBot

# WARNING: These accounts, and their private keys, are publicly known.
COUNCIL_ADDRESS = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8'


@pytest.fixture
def pause_bot(web3_lido_unit, block_data):
    web3_lido_unit.eth.get_block = Mock(return_value=block_data)
    web3_lido_unit.lido.deposit_security_module.get_pause_intent_validity_period_blocks = Mock(return_value=10)
    web3_lido_unit.lido.get_guardian_delegates = Mock(return_value={COUNCIL_ADDRESS: COUNCIL_ADDRESS})
    yield PauserBot(web3_lido_unit)


@pytest.fixture
def pause_message():
    yield {
        'blockHash': '0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c',
        'blockNumber': 10,
        'guardianAddress': COUNCIL_ADDRESS,
        'guardianIndex': 0,
        'stakingModuleId': 1,
        'signature': {
            '_vs': '0xd4933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537',
            'r': '0xbaa668505cd496caaf7117dd074338197200175057909ab73a04463656bdb0fa',
            'recoveryParam': 1,
            's': '0x54933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537',
            'v': 28,
        },
        'type': 'pause',
    }


@pytest.mark.unit
def test_pause_bot_without_messages(pause_bot, block_data):
    pause_bot.message_storage.get_messages_and_actualize = Mock(return_value=[])
    pause_bot._send_pause_message = Mock()
    pause_bot.execute(block_data)
    pause_bot._send_pause_message.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    'block_range',
    [
        4,
        pytest.param(6, marks=pytest.mark.xfail(raises=AssertionError, strict=True)),
    ],
)
def test_pause_bot_outdate_messages(pause_bot, block_data, pause_message, block_range):
    pause_message['blockNumber'] = 5
    pause_bot.message_storage.messages = [pause_message]
    pause_bot.w3.lido.deposit_security_module.get_pause_intent_validity_period_blocks = Mock(return_value=block_range)
    pause_bot._sign_filter = Mock(return_value=lambda _: True)

    pause_bot._send_pause_message = Mock()
    pause_bot.execute(block_data)
    pause_bot._send_pause_message.assert_not_called()


@pytest.mark.unit
def test_pause_bot_clean_messages(pause_bot, block_data, pause_message):
    pause_bot.message_storage.messages = [pause_message]

    pause_bot._sign_filter = Mock(return_value=lambda _: True)

    pause_bot.execute(block_data)
    assert len(pause_bot.message_storage.messages) == 0


GUARDIAN = '0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A'
DELEGATE = '0x5fd0dDbC3351d009eb3f88DE7Cd081a614C519F1'
REVOKED_DELEGATE = '0x43464Fe06c18848a2E2e913194D64c1970f4326a'


@pytest.mark.unit
def test_actualize_filter_drops_revoked_delegate(web3_lido_unit):
    bot = PauserBot(web3_lido_unit)
    web3_lido_unit.eth.get_block = Mock(return_value={'number': 100})
    web3_lido_unit.lido.deposit_security_module.get_pause_intent_validity_period_blocks = Mock(return_value=10)
    web3_lido_unit.lido.get_guardian_delegates = Mock(return_value={DELEGATE: GUARDIAN})

    message_filter = bot._get_message_actualize_filter()
    message = {'guardianAddress': GUARDIAN, 'guardianDelegate': DELEGATE, 'blockNumber': 95}

    assert message_filter(message) is True
    assert message_filter({**message, 'guardianDelegate': REVOKED_DELEGATE}) is False


@pytest.mark.unit
def test_pause_is_not_broadcast_when_simulation_reverts(pause_bot, pause_message, web3_lido_unit):
    web3_lido_unit.lido.deposit_security_module.is_deposits_paused = Mock(return_value=False)
    web3_lido_unit.lido.guardian_delegation_active = Mock(return_value=False)
    web3_lido_unit.transaction = Mock()
    web3_lido_unit.transaction.check = Mock(return_value=False)

    assert pause_bot._send_pause_message(pause_message) is False
    web3_lido_unit.transaction.send.assert_not_called()
