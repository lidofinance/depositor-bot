from math import sqrt


def get_recommended_buffered_ether_to_deposit(gas_fee: int) -> int:
    """Returns suggested minimum buffered ether to deposit (in Wei)"""
    apr = 0.039  # Protocol APR
    # ether/14 days : select sum(tr.value)/1e18 from ethereum."transactions" as tr
    # where tr.to = '\xae7ab96520DE3A18E5e111B5EaAb095312D7fE84'
    # and tr.block_time >= '2021-12-01' and tr.block_time < '2021-12-15' and tr.value < 600*1e18;
    a = 12  # ~ ether/hour
    keys_hour = a / 32
    p = 32 * 10 ** 18 * apr / 365 / 24  # ~ Profit in hour
    cc = 378300  # gas constant for every deposit tx that should be paid
    multiply_constant = 1.5  # we will get profit with constant from 1 to 2, but the most profitable will be 1.5

    return sqrt(multiply_constant * cc * gas_fee * keys_hour / p) * 32 * 10 ** 18
