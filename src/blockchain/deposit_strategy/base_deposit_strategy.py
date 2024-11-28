import abc
import logging

import variables
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from blockchain.deposit_strategy.strategy import DepositStrategy
from blockchain.typings import Web3
from metrics.metrics import DEPOSIT_AMOUNT_OK, DEPOSITABLE_ETHER, GAS_FEE, GAS_OK, POSSIBLE_DEPOSITS_AMOUNT
from web3.types import Wei

logger = logging.getLogger(__name__)


class BaseDepositStrategy(DepositStrategy):
    def __init__(self, w3: Web3, gas_price_calculator: GasPriceCalculator):
        self.w3 = w3
        self._gas_price_calculator = gas_price_calculator

    def can_deposit_keys_based_on_ether(self, module_id: int) -> bool:
        possible_keys = self.deposited_keys_amount(module_id)
        success = self._is_keys_amount_above_threshold(possible_keys, module_id)
        if success:
            base_fee_per_gas = self._gas_price_calculator.get_pending_base_fee()
            success = self._is_deposit_recommended_based_on_keys_amount(possible_keys, base_fee_per_gas, module_id)
        DEPOSIT_AMOUNT_OK.labels(module_id).set(int(success))
        return success

    def _is_keys_amount_above_threshold(self, keys: int, module_id: int) -> bool:
        threshold = self._depositable_keys_threshold()
        success = keys >= threshold
        if not success:
            logger.info(
                {
                    'msg': f'Possible deposits amount is {keys}. Skip deposit.',
                    'module_id': module_id,
                    'threshold': threshold,
                }
            )
        return success

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

    def _depositable_keys_threshold(self) -> int:
        return 1

    def _depositable_ether(self) -> Wei:
        depositable_ether = self.w3.lido.lido.get_depositable_ether()
        DEPOSITABLE_ETHER.set(depositable_ether)
        return depositable_ether

    def deposited_keys_amount(self, module_id: int) -> int:
        depositable_ether = self._depositable_ether()
        possible_deposits_amount = self.w3.lido.staking_router.get_staking_module_max_deposits_count(
            module_id,
            depositable_ether,
        )
        POSSIBLE_DEPOSITS_AMOUNT.labels(module_id).set(possible_deposits_amount)
        return possible_deposits_amount

    @staticmethod
    def _recommended_max_gas(deposits_amount: int, module_id: int):
        # For one key recommended gas fee will be around 10
        # For 10 keys around 100 gwei. For 20 keys ~ 800 gwei
        # ToDo percentiles for all modules?
        recommended_max_gas = (deposits_amount**3 + 100) * 10**8
        logger.info({'msg': 'Calculate recommended max gas based on possible deposits.', 'value': recommended_max_gas})
        GAS_FEE.labels('based_on_buffer_fee', module_id).set(recommended_max_gas)
        return recommended_max_gas

    @abc.abstractmethod
    def _is_deposit_recommended_based_on_keys_amount(self, deposits_amount: int, base_fee: int, module_id: int) -> bool:
        pass

    def get_recommended_fee(self) -> Wei:
        return self._gas_price_calculator.get_recommended_gas_fee()


class DefaultDepositStrategy(BaseDepositStrategy):
    def _is_deposit_recommended_based_on_keys_amount(self, deposits_amount: int, base_fee: int, module_id: int) -> bool:
        return self._recommended_max_gas(deposits_amount, module_id) >= base_fee


class CSMDepositStrategy(BaseDepositStrategy):
    def _is_deposit_recommended_based_on_keys_amount(self, deposits_amount: int, base_fee: int, module_id: int) -> bool:
        return True

    def _depositable_keys_threshold(self) -> int:
        return 2
