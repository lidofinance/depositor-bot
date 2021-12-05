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
