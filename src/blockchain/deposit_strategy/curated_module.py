from blockchain.deposit_strategy.interface import ModuleDepositStrategyInterface
from blockchain.typings import Web3
from web3.types import Wei


class CuratedModuleDepositStrategy(ModuleDepositStrategyInterface):
    """
    Performs deposited keys amount check for regular deposits.
    """

    def __init__(self, w3: Web3):
        super().__init__(w3)

    def _additional_ether(self) -> Wei:
        return Wei(0)
