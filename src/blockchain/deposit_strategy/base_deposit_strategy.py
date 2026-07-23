import logging

from web3.types import Wei

import variables
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from blockchain.deposit_strategy.strategy import DepositStrategy
from blockchain.typings import Web3
from metrics.metrics import GAS_FEE, GAS_OK

logger = logging.getLogger(__name__)


class BaseDepositStrategy(DepositStrategy):
    def __init__(self, w3: Web3, gas_price_calculator: GasPriceCalculator):
        self.w3 = w3
        self._gas_price_calculator = gas_price_calculator

    def is_gas_price_ok(self, module_id: int) -> bool:
        """
        Determines if the gas price is ok for doing a deposit.
        """
        current_gas_fee = self._gas_price_calculator.get_pending_base_fee()
        GAS_FEE.labels('current_fee', module_id).set(current_gas_fee)

        current_buffered_ether = self.w3.lido.lido.get_depositable_ether()
        recommended_gas_fee = self.get_recommended_fee()
        GAS_FEE.labels('recommended_fee', module_id).set(recommended_gas_fee)
        GAS_FEE.labels('max_fee', module_id).set(variables.MAX_GAS_FEE)
        if current_buffered_ether > variables.MAX_BUFFERED_ETHERS:
            success = current_gas_fee <= variables.MAX_GAS_FEE
        else:
            success = recommended_gas_fee >= current_gas_fee
        GAS_OK.labels(module_id).set(int(success))
        return success

    def get_recommended_fee(self) -> Wei:
        return self._gas_price_calculator.get_recommended_gas_fee()


class DefaultDepositStrategy(BaseDepositStrategy):
    pass


class CSMDepositStrategy(BaseDepositStrategy):
    pass
