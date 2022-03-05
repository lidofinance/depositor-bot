import logging

from brownie import web3

from scripts.utils.gas_strategy import GasFeeStrategy
from tests.fixtures.pytest_fixtures import setup_web3_gas_fee_fixtures
from tests.utils.logs import find_log_message


def test_percentile_calculate(caplog, setup_web3_gas_fee_fixtures):
    caplog.set_level(logging.INFO)

    gas_fee_strategy = GasFeeStrategy(web3)
    percentile = gas_fee_strategy.get_gas_fee_percentile(1, 30)

    assert percentile == 83720913390

    # Make sure cache works
    caplog.clear()

    percentile = gas_fee_strategy.get_gas_fee_percentile(1, 20)

    record = find_log_message(caplog, 'Use cached gas history')
    assert record

    assert percentile == 74903359976

    percentile = gas_fee_strategy.get_gas_fee_percentile(1, 50)

    assert percentile == 101522350803


def test_get_recommended_gas_fee(setup_web3_gas_fee_fixtures):
    gas_fee_strategy = GasFeeStrategy(web3)

    fee = gas_fee_strategy.get_recommended_gas_fee([(1, 20), (2, 20)])

    assert fee == gas_fee_strategy.get_gas_fee_percentile(1, 20)

    fee = gas_fee_strategy.get_recommended_gas_fee([(1, 99), (2, 99)])

    assert fee == gas_fee_strategy.max_gas_fee


def test_recommended_buffered_matic():
    gas_fee_strategy = GasFeeStrategy(web3)

    buffered_ether = gas_fee_strategy.get_recommended_buffered_matic_to_delegate(
        10**9)
    assert 1 < buffered_ether / 10**18 < 100

    buffered_ether = gas_fee_strategy.get_recommended_buffered_matic_to_delegate(
        50 * 10**9)
    assert 350 < buffered_ether / 10**18 < 400

    buffered_ether = gas_fee_strategy.get_recommended_buffered_matic_to_delegate(
        70 * 10**9)
    assert 400 < buffered_ether / 10**18 < 600

    buffered_ether = gas_fee_strategy.get_recommended_buffered_matic_to_delegate(
        150 * 10**9)
    assert 600 < buffered_ether / 10**18 < 700
