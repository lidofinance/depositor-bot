import logging

from tests.fixtures.pytest_fixtures import *
from tests.utils.logs import find_log_message


def test_no_pause_messages(
        caplog,
        setup_web3_fixtures_for_pause,
        pause_bot,
        setup_ping_message_to_kafka,
        remove_sleep,
):
    """Just cycle with no pause msg and no pause tx"""
    caplog.set_level(logging.INFO)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    assert not find_log_message(caplog, 'Message pause protocol initiate.')


def test_no_pause_if_protocol_was_paused(
        caplog,
        setup_web3_fixtures_paused,
        pause_bot,
        setup_pause_message_to_kafka,
        remove_sleep,
):
    """Test no pause tx if protocol already paused"""

    caplog.set_level(logging.INFO)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    is_paused = find_log_message(caplog, 'Call `isPaused()')
    assert is_paused.msg['value']
    assert not find_log_message(caplog, 'Message pause protocol initiate.')


def test_pause_msg_receive(
        caplog,
        setup_web3_fixtures_for_pause,
        pause_bot,
        setup_pause_message_to_kafka,
        remove_sleep,
):
    """Retry each time pause tx falls locally or in blockchain"""
    caplog.set_level(logging.INFO)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    assert find_log_message(caplog, 'Message pause protocol initiate.')
    assert find_log_message(caplog, 'No account provided. Skip creating tx.')
    assert not find_log_message(caplog, 'Creating tx in blockchain.')


def test_pause_with_account(
        caplog,
        setup_account,
        setup_web3_fixtures_for_pause,
        pause_bot,
        setup_pause_message_to_kafka,
        remove_sleep,
):
    caplog.set_level(logging.INFO)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    assert find_log_message(caplog, 'Message pause protocol initiate.')
    assert find_log_message(caplog, 'Running in DRY mode.')
    assert not find_log_message(caplog, 'Creating tx in blockchain.')


def test_pause_with_account_in_prod(
        caplog,
        setup_account,
        setup_create_txs,
        setup_web3_fixtures_for_pause,
        pause_bot,
        setup_pause_message_to_kafka,
        remove_sleep,
):
    caplog.set_level(logging.INFO)
    pause_bot.run_cycle()

    assert find_log_message(caplog, 'Fetch `latest` block.')
    assert find_log_message(caplog, 'Message pause protocol initiate.')
    assert find_log_message(caplog, 'Creating tx in blockchain.')


def test_pause_message_filter(
        setup_web3_fixtures_paused,
        pause_bot,
        setup_pause_message_to_kafka,
):
    pause_bot.kafka.update_messages()
    pause_messages = pause_bot.kafka.messages['pause']
    assert pause_messages

    # Message is from block 10
    filtered_pause_messages = pause_bot.kafka.get_pause_messages(13726500, 10)
    assert filtered_pause_messages

    filtered_pause_messages = pause_bot.kafka.get_pause_messages(13726595, 10)
    assert not filtered_pause_messages

    del pause_bot


def test_pause_message_delete(
        setup_web3_fixtures_paused,
        pause_bot,
        setup_pause_message_to_kafka,
):
    pause_bot.kafka.update_messages()
    pause_messages = pause_bot.kafka.messages['pause']
    assert pause_messages

    pause_bot.kafka.clear_pause_messages()
    assert not pause_bot.kafka.messages['pause']
