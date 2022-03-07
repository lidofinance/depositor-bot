import logging
from math import sqrt
from typing import List, Tuple, Iterable

import numpy
from brownie import Wei
from brownie.network.web3 import Web3


logger = logging.getLogger(__name__)


class GasFeeStrategy:
    BLOCKS_IN_ONE_DAY = 6600
    LATEST_BLOCK = 'latest'

    def __init__(self, w3: Web3, blocks_count_cache: int = 300, max_gas_fee: int = Wei('100 gwei')):
        """
        gas_history_block_cache - blocks count that gas his
        """
        self._w3 = w3
        self._blocks_count_cache: int = blocks_count_cache
        self.max_gas_fee = max_gas_fee

        self._gas_fees: list = []

        # Used for caching
        self._latest_fetched_block: int = 0
        self._days_param = None

        # INIT CONSTANTS
        self.apr = 0.044  # Protocol APR
        # ether/14 days : select sum(tr.value)/1e18 from ethereum."transactions" as tr
        # where tr.to = '\xae7ab96520DE3A18E5e111B5EaAb095312D7fE84'
        # and tr.block_time >= '2021-12-01' and tr.block_time < '2021-12-15' and tr.value < 600*1e18;
        self.a = 24  # ~ ether/hour
        self.keys_hour = self.a / 32
        self.p = 32 * 10**18 * self.apr / 365 / 24  # ~ Profit in hour
        self.cc = 378300  # gas constant for every deposit tx that should be paid
        self.ck = 63000  # gas for each key should be paid on deposit
        self.multiply_constant = 1.5  # we will get profit with constant from 1 to 2, but the most profitable will be 1.5

    def _fetch_gas_fee_history(self, days: int) -> List[int]:
        """
        Returns gas fee history for N days.
        Cache updates every {_blocks_count_cache} block.
        """
        latest_block_num = self._w3.eth.get_block('latest')['number']

        # If _blocks_count_cache didn't passed return cache
        if (
            self._latest_fetched_block
            and self._latest_fetched_block + self._blocks_count_cache > latest_block_num
            and self._days_param >= days
        ):
            logger.info({'msg': 'Use cached gas history'})
            return self._gas_fees

        logger.info({'msg': 'Init or refresh gas history.', 'value': {'block_number': latest_block_num}})

        self._latest_fetched_block = latest_block_num
        self._days_param = days

        total_blocks_to_fetch = self.BLOCKS_IN_ONE_DAY * days
        requests_count = total_blocks_to_fetch // 1024 + 1

        gas_fees = []
        last_block = self.LATEST_BLOCK

        for i in range(requests_count):
            stats = self._w3.eth.fee_history(1024, last_block)
            last_block = stats['oldestBlock'] - 2
            gas_fees = stats['baseFeePerGas'] + gas_fees

        self._gas_fees = gas_fees

        return self._gas_fees

    def get_gas_fee_percentile(self, days: int, percentile: int) -> float:
        """Calculates provided percentile for N days"""
        # One week price stats
        gas_fee_history = self._fetch_gas_fee_history(days)
        blocks_to_count_percentile = gas_fee_history[-days * self.BLOCKS_IN_ONE_DAY:]
        gas_percentile = int(numpy.percentile(blocks_to_count_percentile, percentile))
        return gas_percentile

    def get_recommended_gas_fee(self, percentiles: Iterable[Tuple[int, int]], force: bool = False) -> float:
        """Returns the recommended gas fee"""
        if force:
            return self.max_gas_fee

        min_recommended_fee = self.max_gas_fee

        for days, percentile in percentiles:
            min_recommended_fee = min(min_recommended_fee, self.get_gas_fee_percentile(days, percentile))

        return min_recommended_fee

    def is_waiting_beneficial(self, buffered_ether: int, percentile: int, days: int, current_fee, current_recommended_gas_fee):
        gas_fee_history = self._fetch_gas_fee_history(days)
        current_percentile = len([x for x in gas_fee_history[-6600*days:] if x < current_fee])/len(gas_fee_history[-6600*days:]) * 100

        time_between = (current_percentile - percentile) / 100 * days

        time_between_max = (int(buffered_ether / 32) * self.ck + self.cc) * (current_recommended_gas_fee - current_fee) / (int(buffered_ether / 32) * self.p)

        return time_between < time_between_max

    def get_recommended_buffered_ether_to_deposit(self, gas_fee):
        """Returns suggested minimum buffered ether to deposit"""
        return sqrt(self.multiply_constant * self.cc * gas_fee * self.keys_hour / self.p) * 32 * 10**18
