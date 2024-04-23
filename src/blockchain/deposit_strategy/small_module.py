import logging

from web3.types import Wei

from blockchain.deposit_strategy.curated_module import CuratedModuleDepositStrategy
from blockchain.deposit_strategy.interface import ModuleDepositStrategyInterface
from metrics.metrics import GAS_FEE


logger = logging.getLogger(__name__)


class SmallModuleDepositStrategy(CuratedModuleDepositStrategy, ModuleDepositStrategyInterface):
    def _calculate_recommended_gas_based_on_deposit_amount(self, deposits_amount: int) -> Wei:
        # On average, deposits will start with 4 keys with a maximum gas price of 25 Gwei
        recommended_max_gas = deposits_amount ** 4 * 10 ** 8
        logger.info({'msg': 'Calculate recommended max gas based on possible deposits.'})
        GAS_FEE.labels('based_on_buffer_fee', self.module_id).set(recommended_max_gas)
        return recommended_max_gas
