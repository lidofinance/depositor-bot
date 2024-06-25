import logging

from blockchain.contracts.base_interface import ContractInterface
from eth_typing import ChecksumAddress

logger = logging.getLogger(__name__)


class SimpleDVTStakingStrategyContract(ContractInterface):
    abi_path = './interfaces/SimpleDVTStakingStrategy.json'

    def vault(self) -> ChecksumAddress:
        response = self.functions.vault().call()
        logger.info({'msg': 'Call `vault()`.', 'value': response})
        return response

    def get_staking_module(self) -> ChecksumAddress:
        response = self.functions.stakingModule().call()
        logger.info({'msg': 'Call `stakingModule()`.', 'value': response})
        return response
