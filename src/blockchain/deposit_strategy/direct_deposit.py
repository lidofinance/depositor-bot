import logging

from web3.types import Wei

import variables
from blockchain.contracts.staking_module import StakingModuleContract
from blockchain.deposit_strategy.interface import ModuleDepositStrategyInterface
from blockchain.typings import Web3
from metrics.metrics import MELLOW_VAULT_BALANCE

logger = logging.getLogger(__name__)


class DirectDepositStrategy(ModuleDepositStrategyInterface):
    """
    Performs deposited keys amount check for direct deposits.
    """

    def __init__(self, w3: Web3):
        super().__init__(w3)

    def _is_mellow_depositable(
        self,
        module_id: int
    ) -> bool:
        if not variables.MELLOW_CONTRACT_ADDRESS:
            return False
        buffered = self._w3.lido.lido.get_buffered_ether()
        unfinalized = self._w3.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth()
        if buffered < unfinalized:
            return False
        staking_module_contract: StakingModuleContract = self._w3.lido.simple_dvt_staking_strategy.staking_module_contract
        if staking_module_contract.get_staking_module_id() != module_id:
            logger.debug(
                {
                    'msg': 'Mellow module check failed.',
                    'contract_module': staking_module_contract.get_staking_module_id(),
                    'tx_module': module_id
                }
            )
            return False
        balance = self._w3.lido.simple_dvt_staking_strategy.vault_balance()
        MELLOW_VAULT_BALANCE.labels(module_id).set(balance)
        if balance < variables.VAULT_DIRECT_DEPOSIT_THRESHOLD:
            logger.info({'msg': f'{balance} is less than VAULT_DIRECT_DEPOSIT_THRESHOLD while building mellow transaction.'})
            return False
        logger.debug({'msg': 'Mellow module check succeeded.', 'tx_module': module_id})
        return True

    def _additional_ether(self) -> Wei:
        return self._w3.lido.simple_dvt_staking_strategy.vault_balance()

    def is_deposited_keys_amount_ok(self, module_id: int) -> bool:
        try:
            return super().is_deposited_keys_amount_ok(module_id) and self._is_mellow_depositable(module_id)
        except Exception as e:
            logger.warning(
                {
                    'msg': 'Failed to check if mellow depositable',
                    'module_id': module_id,
                    'err': str(e)
                }
            )
            return False
