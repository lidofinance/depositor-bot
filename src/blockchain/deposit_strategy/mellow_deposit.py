import logging

import variables
from blockchain.contracts.staking_module import StakingModuleContract
from blockchain.deposit_strategy.base_deposit_strategy import BaseDepositStrategy
from blockchain.typings import Web3
from metrics.metrics import MELLOW_VAULT_BALANCE
from web3.types import Wei

logger = logging.getLogger(__name__)


class MellowDepositStrategy(BaseDepositStrategy):
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
        buffered = self.w3.lido.lido.get_buffered_ether()
        unfinalized = self.w3.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth()
        if buffered < unfinalized:
            return False
        staking_module_contract: StakingModuleContract = self.w3.lido.simple_dvt_staking_strategy.staking_module_contract
        if staking_module_contract.get_staking_module_id() != module_id:
            logger.debug(
                {
                    'msg': 'Mellow module check failed.',
                    'contract_module': staking_module_contract.get_staking_module_id(),
                    'tx_module': module_id
                }
            )
            return False
        balance = self.w3.lido.simple_dvt_staking_strategy.vault_balance()
        MELLOW_VAULT_BALANCE.labels(module_id).set(balance)
        if balance < variables.VAULT_DIRECT_DEPOSIT_THRESHOLD:
            logger.info({'msg': f'{balance} is less than VAULT_DIRECT_DEPOSIT_THRESHOLD while building mellow transaction.'})
            return False
        logger.debug({'msg': 'Mellow module check succeeded.', 'tx_module': module_id})
        return True

    def _depositable_ether(self) -> Wei:
        depositable_ether = super()._depositable_ether()
        additional_ether = self.w3.lido.simple_dvt_staking_strategy.vault_balance()
        if additional_ether > 0:
            logger.info({'msg': 'Adding mellow vault balance to the depositable check', 'vault': additional_ether})
        depositable_ether += additional_ether
        return depositable_ether

    def deposited_keys_amount(self, module_id: int) -> int:
        try:
            if not self._is_mellow_depositable(module_id):
                return self.DEPOSITABLE_KEYS_THRESHOLD - 1
            return super().deposited_keys_amount(module_id)
        except Exception as e:
            logger.warning(
                {
                    'msg': 'Failed to check if mellow depositable',
                    'module_id': module_id,
                    'err': str(e)
                }
            )
            return False
