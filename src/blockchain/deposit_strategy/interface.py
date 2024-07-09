import logging
from abc import ABC, abstractmethod

from blockchain.typings import Web3
from cryptography.verify_signature import compute_vs
from transport.msg_types.deposit import DepositMessage
from web3.contract.contract import ContractFunction

logger = logging.getLogger(__name__)


class ModuleDepositStrategyInterface(ABC):
    BLOCKS_IN_ONE_DAY = 24 * 60 * 60 // 12

    CACHE_BLOCK_AMOUNT = 300
    REQUEST_SIZE = 1024

    def __init__(self, w3: Web3, module_id: int):
        self.w3 = w3
        self.module_id = module_id
        self._gas_fees: list = []

        # Used for caching
        self._latest_fetched_block: int = 0
        self._days_param: int = 0

    @abstractmethod
    def prepare_and_send(self, quorum: list[DepositMessage], with_flashbots: bool) -> bool:
        pass

    @staticmethod
    def _prepare_signs_for_deposit(quorum: list[DepositMessage]) -> tuple[tuple[str, str], ...]:
        sorted_messages = sorted(quorum, key=lambda msg: int(msg['guardianAddress'], 16))

        return tuple((msg['signature']['r'], compute_vs(msg['signature']['v'], msg['signature']['s'])) for msg in sorted_messages)

    def _send_transaction(
        self,
        tx: ContractFunction,
        flashbots_works: bool
    ) -> bool:
        if tx is None or not self.w3.transaction.check(tx):
            return False
        return self.w3.transaction.send(tx, flashbots_works, 6)
