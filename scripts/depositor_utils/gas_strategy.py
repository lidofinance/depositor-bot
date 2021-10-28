from typing import List

import numpy
from brownie.network.web3 import Web3

from scripts.depositor_utils.logger import logger


class GasFeeStrategy:
    BLOCKS_IN_ONE_DAY = 6600
    LATEST_BLOCK = 'latest'

    def __init__(self, w3: Web3, blocks_count_cache: int = 7800, max_gas_fee: int = None):
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

        logger.info({'msg': 'Init or refetch gas history'})

        self._last_gas_fee_block = self._w3.eth.get_block('latest')['number']
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
        blocks_to_count_percentile = gas_fee_history[:days * self.BLOCKS_IN_ONE_DAY]
        percentile = numpy.percentile(blocks_to_count_percentile, percentile)
        return int(percentile)
