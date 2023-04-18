import logging

from blockchain.contracts import contracts
from bots.pause_bot import PauserBot
from utils.logs import find_log_message
from fixtures.pytest_mocks import *


def test_no_pause_messages(
        caplog,
        setup_web3_fixtures_for_pause,
        remove_sleep,
        remove_transport,
):
    """Just cycle with no pause msg and no pause tx"""
    caplog.set_level(logging.INFO)
    contracts.initialize(setup_web3_fixtures_for_pause)
    pause_bot = PauserBot(setup_web3_fixtures_for_pause)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    assert not find_log_message(caplog, 'Message pause protocol initiate.')


def test_no_pause_if_protocol_was_paused(
    caplog,
    setup_web3_fixtures_paused,
    setup_pause_message_to_kafka,
    remove_sleep,
    remove_transport,
):
    """Test no pause tx if protocol already paused"""
    caplog.set_level(logging.INFO)
    contracts.initialize(setup_web3_fixtures_paused)
    pause_bot = PauserBot(setup_web3_fixtures_paused)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    is_paused_log = find_log_message(caplog, 'Call `getStakingModuleIsActive()`.')
    assert not is_paused_log.msg['value']
    assert not find_log_message(caplog, 'Message pause protocol initiate.')


def test_pause_msg_receive(
    caplog,
    setup_web3_fixtures_for_pause,
    setup_pause_message_to_kafka,
    remove_sleep,
    remove_transport,
):
    """Retry each time pause tx falls locally or in blockchain"""
    caplog.set_level(logging.INFO)
    contracts.initialize(setup_web3_fixtures_for_pause)
    pause_bot = PauserBot(setup_web3_fixtures_for_pause)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    assert find_log_message(caplog, 'Message pause protocol initiate.')
    assert find_log_message(caplog, 'No account provided. Skip creating tx.')


def test_pause_with_account(
        caplog,
        setup_account,
        setup_web3_fixtures_for_pause,
        setup_pause_message_to_kafka,
        remove_sleep,
        remove_transport,
):
    caplog.set_level(logging.INFO)
    contracts.initialize(setup_web3_fixtures_for_pause)
    pause_bot = PauserBot(setup_web3_fixtures_for_pause)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    assert find_log_message(caplog, 'Message pause protocol initiate.')
    assert find_log_message(caplog, 'Running in DRY mode.')


def test_pause_with_account_in_prod(
        caplog,
        setup_account,
        setup_create_txs,
        setup_web3_fixtures_for_pause,
        setup_pause_message_to_kafka,
        remove_sleep,
        remove_transport,
):
    caplog.set_level(logging.INFO)
    contracts.initialize(setup_web3_fixtures_for_pause)
    pause_bot = PauserBot(setup_web3_fixtures_for_pause)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    assert find_log_message(caplog, 'Message pause protocol initiate.')
    assert find_log_message(caplog, 'Send pause transaction.')
