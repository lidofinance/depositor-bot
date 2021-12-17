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

    assert percentile == 100000000000


def test_recommended_buffered_ether():
    gas_fee_strategy = GasFeeStrategy(web3)

    buffered_ether = gas_fee_strategy.get_recommended_buffered_ether_to_deposit(10**9)
    assert 1 < buffered_ether / 10**18 < 100

    buffered_ether = gas_fee_strategy.get_recommended_buffered_ether_to_deposit(50 * 10**9)
    assert 400 < buffered_ether / 10**18 < 700

    buffered_ether = gas_fee_strategy.get_recommended_buffered_ether_to_deposit(70 * 10**9)
    assert 500 < buffered_ether / 10**18 < 1000
