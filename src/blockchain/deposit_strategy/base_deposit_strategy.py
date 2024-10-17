import logging

from blockchain.typings import Web3
from metrics.metrics import DEPOSITABLE_ETHER, GAS_FEE, POSSIBLE_DEPOSITS_AMOUNT
from web3.types import Wei

logger = logging.getLogger(__name__)


class BaseDepositStrategy:
    """
    Attributes:
        DEPOSITABLE_KEYS_THRESHOLD: If the Staking Module has at least THRESHOLD amount of depositable keys, deposits are allowed
    """

    DEPOSITABLE_KEYS_THRESHOLD = 1

    def __init__(self, w3: Web3):
        self.w3 = w3

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
        POSSIBLE_DEPOSITS_AMOUNT.labels(module_id, 0).set(possible_deposits_amount)
        return possible_deposits_amount

    def is_deposit_recommended_based_on_keys_amount(self, deposits_amount: int, base_fee: int, module_id: int) -> bool:
        # For one key recommended gas fee will be around 10
        # For 10 keys around 100 gwei. For 20 keys ~ 800 gwei
        # ToDo percentiles for all modules?
        recommended_max_gas = (deposits_amount**3 + 100) * 10**8
        logger.info({'msg': 'Calculate recommended max gas based on possible deposits.', 'value': recommended_max_gas})
        GAS_FEE.labels('based_on_buffer_fee', module_id).set(recommended_max_gas)
        return recommended_max_gas >= base_fee


class MellowDepositStrategy(BaseDepositStrategy):
    """
    Performs deposited keys amount check for direct deposits.
    """

    def _depositable_ether(self) -> Wei:
        depositable_ether = super()._depositable_ether()
        additional_ether = self.w3.lido.simple_dvt_staking_strategy.vault_balance()
        if additional_ether > 0:
            logger.info({'msg': 'Adding mellow vault balance to the depositable check', 'vault': additional_ether})
        depositable_ether += additional_ether
        return depositable_ether

    def deposited_keys_amount(self, module_id: int) -> int:
        depositable_ether = self._depositable_ether()
        possible_deposits_amount_assumption = self.w3.lido.staking_router.get_staking_module_max_deposits_count(
            module_id,
            depositable_ether,
        )
        possible_deposited_eth = Web3.to_wei(32 * possible_deposits_amount_assumption, 'ether')
        possible_deposits_amount = self.w3.lido.staking_router.get_staking_module_max_deposits_count(
            module_id,
            possible_deposited_eth,
        )
        POSSIBLE_DEPOSITS_AMOUNT.labels(module_id, 1).set(possible_deposits_amount)
        return possible_deposits_amount if possible_deposits_amount_assumption == possible_deposits_amount else 0


class CSMDepositStrategy:
    DEPOSITABLE_KEYS_THRESHOLD = 2

    def is_deposit_recommended_based_on_keys_amount(self, deposits_amount: int, base_fee: int, module_id: int) -> bool:
        return True
