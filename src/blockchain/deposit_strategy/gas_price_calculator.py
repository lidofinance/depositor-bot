# pyright: reportTypedDictNotRequiredAccess=false

import logging
from typing import Literal

import numpy
import variables
from blockchain.deposit_strategy.base_deposit_strategy import BaseDepositStrategy
from blockchain.typings import Web3
from eth_typing import BlockNumber
from metrics.metrics import DEPOSIT_AMOUNT_OK, GAS_FEE, GAS_OK
from web3.types import Wei

logger = logging.getLogger(__name__)


class GasPriceCalculator:
    _BLOCKS_IN_ONE_DAY = 24 * 60 * 60 // 12
    _REQUEST_SIZE = 1024
    _PER_KEY_PRICE_ASSUMPTION = Web3.to_wei(100, 'gwei')

    def __init__(self, w3: Web3):
        self.w3 = w3

    def is_gas_price_ok(self, module_id: int) -> bool:
        """
        Determines if the gas price is ok for doing a deposit.
        """
        current_gas_fee = self._get_pending_base_fee()
        GAS_FEE.labels('current_fee', module_id).set(current_gas_fee)

        depositable_ether = self.w3.lido.lido.get_depositable_ether()
        if depositable_ether > variables.MAX_BUFFERED_ETHERS:
            success = current_gas_fee <= variables.MAX_GAS_FEE
        else:
            recommended_gas_fee = self._get_recommended_gas_fee()
            GAS_FEE.labels('recommended_fee', module_id).set(recommended_gas_fee)
            GAS_FEE.labels('max_fee', module_id).set(variables.MAX_GAS_FEE)
            success = recommended_gas_fee >= current_gas_fee
        GAS_OK.labels(module_id).set(int(success))
        return success

    def _get_pending_base_fee(self) -> Wei:
        base_fee_per_gas = self.w3.eth.get_block('pending')['baseFeePerGas']
        logger.info({'msg': 'Fetch base_fee_per_gas for pending block.', 'value': base_fee_per_gas})
        return base_fee_per_gas

    def calculate_deposit_recommendation(self, deposit_strategy: BaseDepositStrategy, module_id: int) -> bool:
        is_gas_ok = self.is_gas_price_ok(module_id)
        logger.info({'msg': 'Calculate gas recommendations.', 'value': is_gas_ok})

        possible_keys = deposit_strategy.deposited_keys_amount(module_id)
        success = False
        if possible_keys < deposit_strategy.DEPOSITABLE_KEYS_THRESHOLD:
            logger.info(
                {
                    'msg': f'Possible deposits amount is {possible_keys}. Skip deposit.',
                    'module_id': module_id,
                    'threshold': deposit_strategy.DEPOSITABLE_KEYS_THRESHOLD,
                }
            )
        else:
            recommended_max_gas = GasPriceCalculator._calculate_recommended_gas_based_on_deposit_amount(
                possible_keys,
                module_id,
            )
            base_fee_per_gas = self._get_pending_base_fee()
            success = recommended_max_gas >= base_fee_per_gas
            if not is_gas_ok or not success:
                gas_price_diff = self._get_pending_base_fee() - self._get_recommended_gas_fee()
                aprx_waiting_time = gas_price_diff * percentail_in_days  # noqa
                possible_income = aprx_waiting_time * self.w3.lido.lido.get_depositable_ether() * 0.03
                success = is_gas_ok = possible_income >= gas_price_diff + recommended_max_gas
        DEPOSIT_AMOUNT_OK.labels(module_id).set(int(success))
        return is_gas_ok and success

    @staticmethod
    def _calculate_recommended_gas_based_on_deposit_amount(deposits_amount: int, module_id: int) -> int:
        # For one key recommended gas fee will be around 10
        # For 10 keys around 100 gwei. For 20 keys ~ 800 gwei
        # ToDo percentiles for all modules?
        recommended_max_gas = (deposits_amount**3 + 100) * 10**8
        logger.info({'msg': 'Calculate recommended max gas based on possible deposits.', 'value': recommended_max_gas})
        GAS_FEE.labels('based_on_buffer_fee', module_id).set(recommended_max_gas)
        return recommended_max_gas

    def _get_recommended_gas_fee(self) -> Wei:
        gas_history = self._fetch_gas_fee_history(variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1)
        return Wei(int(numpy.percentile(gas_history, variables.GAS_FEE_PERCENTILE_1)))

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
