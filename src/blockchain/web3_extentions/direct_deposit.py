import logging

import variables
from blockchain.contracts.staking_module import StakingModuleContract
from blockchain.typings import Web3
from metrics.metrics import MELLOW_VAULT_BALANCE

logger = logging.getLogger(__name__)


def is_mellow_depositable(
    w3: Web3,
    module_id: int
) -> bool:
    if not variables.MELLOW_CONTRACT_ADDRESS:
        return False
    try:
        if w3.lido.lido.get_buffered_ether() < w3.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth():
            return False
        staking_module_contract: StakingModuleContract = w3.lido.simple_dvt_staking_strategy.staking_module_contract
        if staking_module_contract.get_staking_module_id() != module_id:
            logger.debug(
                {
                    'msg': 'Mellow module check failed.',
                    'contract_module': staking_module_contract.get_staking_module_id(),
                    'tx_module': module_id
                }
            )
            return False
        balance = w3.lido.simple_dvt_staking_strategy.vault_balance()
    except Exception as e:
        logger.warning(
            {
                'msg': 'Failed to check if mellow depositable',
                'module_id': str(module_id),
                'err': str(e)
            }
        )
        return False
    MELLOW_VAULT_BALANCE.labels(module_id).set(balance)
    if balance < variables.VAULT_DIRECT_DEPOSIT_THRESHOLD:
        logger.info({'msg': f'{balance} is less than VAULT_DIRECT_DEPOSIT_THRESHOLD while building mellow transaction.'})
        return False
    return True
