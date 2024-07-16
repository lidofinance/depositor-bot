import logging
from abc import ABC, abstractmethod

from web3.types import Wei

from blockchain.deposit_strategy.gas_price_verifier import GasPriceCalculator, get_pending_base_fee
from blockchain.typings import Web3
from metrics.metrics import DEPOSITABLE_ETHER, POSSIBLE_DEPOSITS_AMOUNT

logger = logging.getLogger(__name__)


class ModuleDepositStrategyInterface(ABC):
    _DEPOSITABLE_KEYS_THRESHOLD = 0

    def __init__(self, w3: Web3):
        self._w3 = w3

    def _get_possible_deposits_amount(self, module_id: int) -> int:
        depositable_ether = self._w3.lido.lido.get_depositable_ether()
        additional_ether = self._additional_ether()
        if additional_ether > 0:
            logger.info({'msg': 'Adding mellow vault balance to the depositable check', 'vault': additional_ether})
        depositable_ether += additional_ether
        DEPOSITABLE_ETHER.labels(module_id).set(depositable_ether)

        possible_deposits_amount = self._w3.lido.staking_router.get_staking_module_max_deposits_count(
            module_id,
            depositable_ether,
        )
        POSSIBLE_DEPOSITS_AMOUNT.labels(module_id).set(possible_deposits_amount)
        return possible_deposits_amount

    @abstractmethod
    def _additional_ether(self) -> Wei:
        pass

    def is_deposited_keys_amount_ok(self, module_id: int) -> bool:
        possible_deposits_amount = self._get_possible_deposits_amount(module_id)

        if possible_deposits_amount <= self._DEPOSITABLE_KEYS_THRESHOLD:
            logger.info(
                {
                    'msg': f'Possible deposits amount is {possible_deposits_amount}. Skip deposit.',
                    'module_id': module_id,
                    'threshold': self._DEPOSITABLE_KEYS_THRESHOLD,
                }
            )
            return False

        recommended_max_gas = GasPriceCalculator.calculate_recommended_gas_based_on_deposit_amount(
            possible_deposits_amount,
            module_id,
        )
        base_fee_per_gas = get_pending_base_fee(self._w3)
        success = recommended_max_gas >= base_fee_per_gas
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': success})
        return success
