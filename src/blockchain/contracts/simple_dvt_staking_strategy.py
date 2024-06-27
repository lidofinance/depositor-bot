import logging
from typing import cast

from blockchain.contracts.base_interface import ContractInterface
from blockchain.contracts.staking_module import StakingModuleContract
from eth_typing import BlockIdentifier, ChecksumAddress

logger = logging.getLogger(__name__)


class SimpleDVTStakingStrategyContract(ContractInterface):
    abi_path = './interfaces/SimpleDVTStakingStrategy.json'

    def vault(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.vault().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `vault()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def get_staking_module(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.stakingModule().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `stakingModule()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    @property
    def staking_module_contract(self) -> StakingModuleContract:
        return cast(
            StakingModuleContract,
            self.w3.eth.contract(
                address=self.get_staking_module(),
                ContractFactoryClass=StakingModuleContract,
            )
        )
