# pyright: reportTypedDictNotRequiredAccess=false

import logging
from typing import Literal

import numpy
import variables
from blockchain.typings import Web3
from eth_typing import BlockNumber
from web3.types import Wei

logger = logging.getLogger(__name__)


class GasPriceCalculator:
    _BLOCKS_IN_ONE_DAY = 24 * 60 * 60 // 12
    _REQUEST_SIZE = 1024

    def __init__(self, w3: Web3):
        self.w3 = w3

    def get_pending_base_fee(self) -> Wei:
        base_fee_per_gas = self.w3.eth.get_block('pending')['baseFeePerGas']
        logger.info({'msg': 'Fetch base_fee_per_gas for pending block.', 'value': base_fee_per_gas})
        return base_fee_per_gas

    def get_recommended_gas_fee(self) -> Wei:
        gas_history = self._fetch_gas_fee_history(variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1)
        return Wei(int(numpy.percentile(gas_history, variables.GAS_FEE_PERCENTILE_1))) + variables.GAS_ADDENDUM

    def _fetch_gas_fee_history(self, days: int) -> list[int]:
        latest_block_num = self.w3.eth.get_block('latest')['number']
        logger.info({'msg': 'Fetch gas fee history.', 'value': {'block_number': latest_block_num}})

        total_blocks_to_fetch = self._BLOCKS_IN_ONE_DAY * days
        requests_count = total_blocks_to_fetch // self._REQUEST_SIZE + 1

        gas_fees = []
        last_block: Literal['latest'] | BlockNumber = 'latest'

        for _ in range(requests_count):
            stats = self.w3.eth.fee_history(self._REQUEST_SIZE, last_block, [])
            last_block = BlockNumber(stats['oldestBlock'] - 2)
            gas_fees = stats['baseFeePerGas'] + gas_fees
        return gas_fees[: days * self._BLOCKS_IN_ONE_DAY]
