# pyright: reportTypedDictNotRequiredAccess=false

import logging
from typing import Literal

import numpy
from eth_typing import BlockNumber
from web3.types import Wei

import variables
from blockchain.typings import Web3
from metrics.metrics import GAS_FEE

logger = logging.getLogger(__name__)


def get_pending_base_fee(w3: Web3) -> Wei:
    base_fee_per_gas = w3.eth.get_block('pending')['baseFeePerGas']
    logger.info({'msg': 'Fetch base_fee_per_gas for pending block.', 'value': base_fee_per_gas})
    return base_fee_per_gas


class GasPriceCalculator:
    _BLOCKS_IN_ONE_DAY = 24 * 60 * 60 // 12
    _REQUEST_SIZE = 1024

    def __init__(self, w3: Web3):
        self._w3 = w3

    def is_gas_price_ok(self, module_id: int) -> bool:
        """
        Determines if the gas price is ok for doing a deposit.
        """
        current_gas_fee = get_pending_base_fee(self._w3)
        GAS_FEE.labels('current_fee', module_id).set(current_gas_fee)

        current_buffered_ether = self._w3.lido.lido.get_depositable_ether()
        if current_buffered_ether > variables.MAX_BUFFERED_ETHERS:
            return current_gas_fee <= variables.MAX_GAS_FEE

        recommended_gas_fee = self._get_recommended_gas_fee()
        GAS_FEE.labels('recommended_fee', module_id).set(recommended_gas_fee)
        GAS_FEE.labels('max_fee', module_id).set(variables.MAX_GAS_FEE)
        return recommended_gas_fee >= current_gas_fee

    @staticmethod
    def calculate_recommended_gas_based_on_deposit_amount(deposits_amount: int, module_id: int) -> int:
        # For one key recommended gas fee will be around 10
        # For 10 keys around 100 gwei. For 20 keys ~ 800 gwei
        # ToDo percentiles for all modules?
        recommended_max_gas = (deposits_amount ** 3 + 100) * 10 ** 8
        logger.info({'msg': 'Calculate recommended max gas based on possible deposits.', 'value': recommended_max_gas})
        GAS_FEE.labels('based_on_buffer_fee', module_id).set(recommended_max_gas)
        return recommended_max_gas

    def _get_recommended_gas_fee(self) -> Wei:
        gas_history = self._fetch_gas_fee_history(variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1)
        return Wei(int(numpy.percentile(gas_history, variables.GAS_FEE_PERCENTILE_1)))

    def _fetch_gas_fee_history(self, days: int) -> list[int]:
        latest_block_num = self._w3.eth.get_block('latest')['number']
        logger.info({'msg': 'Fetch gas fee history.', 'value': {'block_number': latest_block_num}})

        total_blocks_to_fetch = self._BLOCKS_IN_ONE_DAY * days
        requests_count = total_blocks_to_fetch // self._REQUEST_SIZE + 1

        gas_fees = []
        last_block: Literal['latest'] | BlockNumber = 'latest'

        for _ in range(requests_count):
            stats = self._w3.eth.fee_history(self._REQUEST_SIZE, last_block, [])
            last_block = BlockNumber(stats['oldestBlock'] - 2)
            gas_fees = stats['baseFeePerGas'] + gas_fees
        return gas_fees[: days * self._BLOCKS_IN_ONE_DAY]
