from unittest.mock import Mock

import pytest

import variables
from bots.pause import PauserBot


@pytest.fixture
def pause_bot(web3_lido_unit, block_data):
    web3_lido_unit.eth.get_block = Mock(return_value=block_data)
    variables.MESSAGE_TRANSPORTS = ''
    web3_lido_unit.lido.deposit_security_module.get_pause_intent_validity_period_blocks = Mock(return_value=10)
    yield PauserBot(web3_lido_unit)


@pytest.fixture
def pause_message():
    yield {
        "blockHash": "0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c",
        "blockNumber": 10,
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
    }


@pytest.mark.unit
def test_pause_bot_without_messages(pause_bot, block_data):
    pause_bot.message_storage.get_messages = Mock(return_value=[])
    pause_bot._send_pause_message = Mock()
    pause_bot.execute(block_data)
    pause_bot._send_pause_message.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "block_range",
    [4, pytest.param(6, marks=pytest.mark.xfail)],
)
def test_pause_bot_outdate_messages(pause_bot, block_data, pause_message, block_range):
    pause_message['blockNumber'] = 5
    pause_bot.message_storage.messages = [pause_message]
    pause_bot.w3.lido.deposit_security_module.get_pause_intent_validity_period_blocks = Mock(return_value=block_range)

    pause_bot._send_pause_message = Mock()
    pause_bot.execute(block_data)
    pause_bot._send_pause_message.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "active_module",
    [False, pytest.param(True, marks=pytest.mark.xfail)],
)
def test_pause_bot_clean_messages(pause_bot, block_data, pause_message, active_module):
    pause_bot.message_storage.messages = [pause_message]
    pause_bot.w3.lido.staking_router.is_staking_module_active = Mock(return_value=active_module)

    pause_bot.execute(block_data)
    assert len(pause_bot.message_storage.messages) == 0


@pytest.mark.unit
def test_pause_message_filtered_by_module_id(pause_bot, block_data, pause_message):
    new_message = pause_message.copy()
    new_message['stakingModuleId'] = 2

    pause_bot.message_storage.messages = [pause_message, pause_message, new_message]
    pause_bot.w3.lido.staking_router.is_staking_module_active = lambda module_id: not module_id % 2

    pause_bot.execute(block_data)

    # Only module_id=1 messages filtered
    assert len(pause_bot.message_storage.messages) == 1
