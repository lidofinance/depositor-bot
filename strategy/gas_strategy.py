import math

from brownie import Wei
from brownie.network import web3
from brownie.network.gas.strategies import GasNowScalingStrategy


def get_scaling_in_time_gas_strategy(
    max_waiting_time: int,
    max_gas_price: Wei,
    increment: float = 1.1,
) -> GasNowScalingStrategy:
    """
    Returns strategy that will increase gas_price each N blocks if transaction was not Submitted.
    Where N - is exactly amount of block that after `max_waiting_time` passed, price will reach to `max_gas_price`.

    :param max_waiting_time: Time in seconds.
    :param max_gas_price: Max gas price that we are going to spend on transaction.
    :param increment: Gas price will be increased by multiplying the previous gas price by `increment`.
    """
    min_gas_price = web3.eth.generate_gas_price()
    avg_block_time = 13

    block_duration = int(max_waiting_time / avg_block_time / math.log(max_gas_price / min_gas_price, increment))

    return GasNowScalingStrategy(
        initial_speed='slow',
        max_speed='rapid',
        increment=increment,
        block_duration=block_duration,
        max_gas_price=max_gas_price,
    )
