import logging

from blockchain.gas_strategy import GasFeeStrategy
from utils.logs import find_log_message
from fixtures.pytest_mocks import *


def test_percentile_calculate(caplog, web3_gas_fee):
    caplog.set_level(logging.INFO)

    gas_fee_strategy = GasFeeStrategy(web3_gas_fee)
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


def test_get_recommended_gas_fee(web3_gas_fee):
    gas_fee_strategy = GasFeeStrategy(web3_gas_fee)

    fee = gas_fee_strategy.get_recommended_gas_fee([(1, 20), (2, 20)])

    assert fee == gas_fee_strategy.get_gas_fee_percentile(1, 20)

    fee = gas_fee_strategy.get_recommended_gas_fee([(1, 99), (2, 99)])

    assert fee == gas_fee_strategy.max_gas_fee
