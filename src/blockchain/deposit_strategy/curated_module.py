# pyright: reportTypedDictNotRequiredAccess=false

import logging
from typing import Literal

import numpy
import variables
from blockchain.deposit_strategy.interface import ModuleDepositStrategyInterface
from blockchain.typings import Web3
from blockchain.web3_extentions.direct_deposit import is_mellow_depositable
from eth_typing import BlockNumber
from metrics.metrics import DEPOSITABLE_ETHER, GAS_FEE, POSSIBLE_DEPOSITS_AMOUNT
from web3.types import Wei

logger = logging.getLogger(__name__)


class CuratedModuleDepositStrategy(ModuleDepositStrategyInterface):
    BLOCKS_IN_ONE_DAY = 24 * 60 * 60 // 12

    CACHE_BLOCK_AMOUNT = 300
    REQUEST_SIZE = 1024

    def __init__(self, w3: Web3, module_id: int):
        super().__init__(w3, module_id)

        self._gas_fees: list = []

        # Used for caching
        self._latest_fetched_block: int = 0
        self._days_param: int = 0

    def is_deposited_keys_amount_ok(self) -> bool:
        possible_deposits_amount = self._get_possible_deposits_amount()

        if possible_deposits_amount == 0:
            logger.info(
                {
                    'msg': f'Possible deposits amount is {possible_deposits_amount}. Skip deposit.',
                    'module_id': str(self.module_id),
                }
            )
            return False

        recommended_max_gas = self._calculate_recommended_gas_based_on_deposit_amount(possible_deposits_amount)

        base_fee_per_gas = self._get_pending_base_fee()
        return recommended_max_gas >= base_fee_per_gas

    def _get_possible_deposits_amount(self) -> int:
        depositable_ether = self.w3.lido.lido.get_depositable_ether()
        if (is_mellow_depositable(self.w3, self.module_id) and
            self.w3.lido.lido.get_depositable_ether() >= self.w3.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth()):
            depositable_ether += self.w3.lido.simple_dvt_staking_strategy.vault_balance()
        DEPOSITABLE_ETHER.labels(self.module_id).set(depositable_ether)

        possible_deposits_amount = self.w3.lido.staking_router.get_staking_module_max_deposits_count(
            self.module_id,
            depositable_ether,
        )
        POSSIBLE_DEPOSITS_AMOUNT.labels(self.module_id).set(possible_deposits_amount)
        return possible_deposits_amount

    def _calculate_recommended_gas_based_on_deposit_amount(self, deposits_amount: int) -> int:
        # For one key recommended gas fee will be around 10
        # For 10 keys around 100 gwei. For 20 keys ~ 800 gwei
        # ToDo percentiles for all modules?
        recommended_max_gas = (deposits_amount ** 3 + 100) * 10 ** 8
        logger.info({'msg': 'Calculate recommended max gas based on possible deposits.', 'value': recommended_max_gas})
        GAS_FEE.labels('based_on_buffer_fee', self.module_id).set(recommended_max_gas)
        return recommended_max_gas

    def _get_pending_base_fee(self) -> Wei:
        base_fee_per_gas = self.w3.eth.get_block('pending')['baseFeePerGas']
        logger.info({'msg': 'Fetch base_fee_per_gas for pending block.', 'value': base_fee_per_gas})
        return base_fee_per_gas

    def is_gas_price_ok(self) -> bool:
        current_gas_fee = self._get_pending_base_fee()
        GAS_FEE.labels('current_fee', self.module_id).set(current_gas_fee)

        recommended_gas_fee = self._get_recommended_gas_fee()
        GAS_FEE.labels('recommended_fee', self.module_id).set(recommended_gas_fee)

        GAS_FEE.labels('max_fee', self.module_id).set(variables.MAX_GAS_FEE)

        current_buffered_ether = self.w3.lido.lido.get_depositable_ether()
        if current_buffered_ether > variables.MAX_BUFFERED_ETHERS:
            return current_gas_fee <= variables.MAX_GAS_FEE

        return recommended_gas_fee >= current_gas_fee

    def _get_recommended_gas_fee(self) -> Wei:
        gas_history = self._fetch_gas_fee_history(variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1)
        return Wei(int(numpy.percentile(gas_history, variables.GAS_FEE_PERCENTILE_1)))

    def _fetch_gas_fee_history(self, days: int) -> list[int]:
        latest_block_num = self.w3.eth.get_block('latest')['number']

        if (
            self._latest_fetched_block
            and self._latest_fetched_block + self.CACHE_BLOCK_AMOUNT > latest_block_num
            and self._days_param >= days
        ):
            logger.info({'msg': 'Use cached gas history'})
            return self._gas_fees

        logger.info({'msg': 'Fetch gas fee history.', 'value': {'block_number': latest_block_num}})

        self._latest_fetched_block = latest_block_num
        self._days_param = days

        total_blocks_to_fetch = self.BLOCKS_IN_ONE_DAY * days
        requests_count = total_blocks_to_fetch // self.REQUEST_SIZE + 1

        gas_fees = []
        last_block: Literal['latest'] | BlockNumber = 'latest'

        for _ in range(requests_count):
            stats = self.w3.eth.fee_history(self.REQUEST_SIZE, last_block, [])
            last_block = BlockNumber(stats['oldestBlock'] - 2)
            gas_fees = stats['baseFeePerGas'] + gas_fees

        self._gas_fees = gas_fees[: days * self.BLOCKS_IN_ONE_DAY]

        return self._gas_fees
