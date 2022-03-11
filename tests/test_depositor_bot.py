import logging

from tests.fixtures.pytest_fixtures import *
from tests.utils.logs import find_log_message


ISSUES_FOUND_LOG = 'Issues found.'
ISSUES_NOT_FOUND_LOG = 'No issues found.'


def test_deposit_issues__account_balance(
    caplog,
    setup_web3_deposit_fixtures_small_balance,
    depositor_bot,
    remove_sleep,
    setup_ping_message_to_kafka,
    setup_deposit_message_to_kafka,
    setup_account,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert find_log_message(caplog, depositor_bot.NOT_ENOUGH_BALANCE_ON_ACCOUNT)
    record = find_log_message(caplog, ISSUES_FOUND_LOG)
    assert record
    assert record.msg['value'] == [depositor_bot.NOT_ENOUGH_BALANCE_ON_ACCOUNT]
    assert not find_log_message(caplog, ISSUES_NOT_FOUND_LOG)


def test_deposit_issues__gas_strategy(
        caplog,
        setup_web3_deposit_fixtures_with_high_gas,
        depositor_bot,
        remove_sleep,
        setup_ping_message_to_kafka,
        setup_deposit_message_to_kafka,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert find_log_message(caplog, depositor_bot.GAS_FEE_HIGHER_THAN_RECOMMENDED)
    record = find_log_message(caplog, ISSUES_FOUND_LOG)
    assert record
    assert record.msg['value'] == [depositor_bot.GAS_FEE_HIGHER_THAN_RECOMMENDED]
    assert not find_log_message(caplog, ISSUES_NOT_FOUND_LOG)


def test_deposit_issues__security_check(
    caplog,
    setup_web3_deposit_fixtures_prohibits_the_deposit,
    depositor_bot,
    remove_sleep,
    setup_ping_message_to_kafka,
    setup_deposit_message_to_kafka,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert find_log_message(caplog, depositor_bot.DEPOSIT_SECURITY_ISSUE)
    record = find_log_message(caplog, ISSUES_FOUND_LOG)
    assert record
    assert record.msg['value'] == [depositor_bot.DEPOSIT_SECURITY_ISSUE]
    assert not find_log_message(caplog, ISSUES_NOT_FOUND_LOG)


def test_deposit_issues__buffered_ether(
    caplog,
    setup_web3_deposit_fixtures_not_enough_buffered_ether,
    depositor_bot,
    remove_sleep,
    setup_ping_message_to_kafka,
    setup_deposit_message_to_kafka,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert find_log_message(caplog, depositor_bot.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)
    record = find_log_message(caplog, ISSUES_FOUND_LOG)
    assert record
    assert record.msg['value'] == [depositor_bot.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER]
    assert not find_log_message(caplog, ISSUES_NOT_FOUND_LOG)


def test_deposit_issues__enough_signs(
        caplog,
        setup_web3_deposit_fixtures,
        depositor_bot,
        remove_sleep,
        setup_ping_message_to_kafka,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert find_log_message(caplog, depositor_bot.QUORUM_IS_NOT_READY)
    record = find_log_message(caplog, ISSUES_FOUND_LOG)
    assert record
    assert record.msg['value'] == [depositor_bot.QUORUM_IS_NOT_READY]
    assert not find_log_message(caplog, ISSUES_NOT_FOUND_LOG)


def test_deposit_issues__no_free_keys(
    caplog,
    setup_web3_deposit_fixtures_no_free_keys,
    depositor_bot,
    remove_sleep,
    setup_ping_message_to_kafka,
    setup_deposit_message_to_kafka,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert find_log_message(caplog, depositor_bot.LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS)
    record = find_log_message(caplog, ISSUES_FOUND_LOG)
    assert record
    assert record.msg['value'] == [depositor_bot.LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS]
    assert not find_log_message(caplog, ISSUES_NOT_FOUND_LOG)


def test_depositor_bot__no_account(
    caplog,
    setup_web3_deposit_fixtures,
    depositor_bot,
    setup_deposit_message_to_kafka,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert not find_log_message(caplog, ISSUES_FOUND_LOG)
    assert find_log_message(caplog, ISSUES_NOT_FOUND_LOG)
    assert find_log_message(caplog, 'Account was not provided.')
    assert not find_log_message(caplog, 'Creating tx in blockchain.')


def test_depositor_bot__no_create_tx(
    caplog,
    setup_web3_deposit_fixtures,
    depositor_bot,
    setup_deposit_message_to_kafka,
    setup_account,
    remove_sleep,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert not find_log_message(caplog, ISSUES_FOUND_LOG)
    assert find_log_message(caplog, ISSUES_NOT_FOUND_LOG)
    assert find_log_message(caplog, 'Run in dry mode.')
    assert not find_log_message(caplog, 'Creating tx in blockchain.')


def test_depositor_bot__deposit(
    caplog,
    setup_web3_deposit_fixtures,
    depositor_bot,
    setup_ping_message_to_kafka,
    setup_deposit_message_to_kafka,
    setup_account,
    setup_create_txs,
    remove_sleep,
):
    caplog.set_level(logging.INFO)
    depositor_bot.run_cycle()

    assert not find_log_message(caplog, ISSUES_FOUND_LOG)
    assert find_log_message(caplog, ISSUES_NOT_FOUND_LOG)
    assert find_log_message(caplog, 'Creating tx in blockchain.')


def test_depositor_bot__signs_grouping(
    caplog,
    setup_web3_deposit_fixtures,
    setup_deposit_messages_to_kafka,
    depositor_bot,
):
    caplog.set_level(logging.INFO)
    depositor_bot._update_state()
    sorted_signs = depositor_bot._get_deposit_params(depositor_bot.deposit_root, depositor_bot.keys_op_index)

    assert len(sorted_signs) == 3


def test_depositor_bot_priority_fee(
    setup_web3_deposit_fixtures,
    depositor_bot,
):
    priority_fee = depositor_bot._get_deposit_priority_fee(0)
    assert 10 * 10**9 >= priority_fee >= 2 * 10**9

    priority_fee = depositor_bot._get_deposit_priority_fee(55)
    assert 10 * 10**9 >= priority_fee >= 2 * 10**9

    priority_fee = depositor_bot._get_deposit_priority_fee(100)
    assert 10 * 10**9 >= priority_fee >= 2 * 10**9
