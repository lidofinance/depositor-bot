import logging
from abc import ABC, abstractmethod

from blockchain.typings import Web3
from metrics.metrics import DEPOSITABLE_ETHER, POSSIBLE_DEPOSITS_AMOUNT
from web3.types import Wei

logger = logging.getLogger(__name__)


class DepositStrategy(ABC):
    """
        Attributes:
            DEPOSITABLE_KEYS_THRESHOLD If you have at least TRESHOLD keys, you can deposit
    """
    DEPOSITABLE_KEYS_THRESHOLD = 1

    @abstractmethod
    def deposited_keys_amount(self, module_id: int) -> int:
        pass


class BaseDepositStrategy(DepositStrategy):
    def __init__(self, w3: Web3):
        self.w3 = w3

    def _get_possible_deposits_amount(self, module_id: int) -> int:
        depositable_ether = self._depositable_ether()
        DEPOSITABLE_ETHER.labels(module_id).set(depositable_ether)

        possible_deposits_amount = self.w3.lido.staking_router.get_staking_module_max_deposits_count(
            module_id,
            depositable_ether,
        )
        POSSIBLE_DEPOSITS_AMOUNT.labels(module_id).set(possible_deposits_amount)
        return possible_deposits_amount

    def _depositable_ether(self) -> Wei:
        return self.w3.lido.lido.get_depositable_ether()

    def deposited_keys_amount(self, module_id: int) -> int:
        depositable_ether = self._depositable_ether()
        DEPOSITABLE_ETHER.labels(module_id).set(depositable_ether)

        possible_deposits_amount = self.w3.lido.staking_router.get_staking_module_max_deposits_count(
            module_id,
            depositable_ether,
        )
        POSSIBLE_DEPOSITS_AMOUNT.labels(module_id).set(possible_deposits_amount)
        return possible_deposits_amount
