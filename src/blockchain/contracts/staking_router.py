import logging

from blockchain.contracts.base_interface import ContractInterface
from web3.types import BlockIdentifier, Wei

logger = logging.getLogger(__name__)


class StakingRouterContractV2(ContractInterface):
    abi_path = './interfaces/StakingRouterV2.json'

    def get_contract_version(self, block_identifier: BlockIdentifier = 'latest') -> int:
        response = self.functions.getContractVersion().call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': 'Call `getContractVersion()`.',
                'value': response,
                'block_identifier': block_identifier.__repr__(),
            }
        )
        return response

    def get_staking_module_ids(self, block_identifier: BlockIdentifier = 'latest') -> list[int]:
        """Returns the ids of all registered staking modules"""
        response = self.functions.getStakingModuleIds().call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': 'Call `getStakingModuleIds()`.',
                'value': response,
                'block_identifier': block_identifier.__repr__(),
            }
        )
        return response

    def get_staking_module_digests(self, module_ids: list[int], block_identifier: BlockIdentifier = 'latest') -> list[dict]:
        """Returns staking module digest for passed staking module ids"""
        response = self.functions.getStakingModuleDigests(module_ids).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `getStakingModuleDigests({module_ids})`.',
                'value': response,
                'block_identifier': block_identifier.__repr__(),
            }
        )
        return response

    def is_staking_module_active(
        self,
        staking_module_id: int,
        block_identifier: BlockIdentifier = 'latest',
    ) -> bool:
        response = self.functions.getStakingModuleIsActive(staking_module_id).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `getStakingModuleIsActive({staking_module_id})`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    def get_staking_module_nonce(
        self,
        staking_module_id: int,
        block_identifier: BlockIdentifier = 'latest',
    ) -> int:
        response = self.functions.getStakingModuleNonce(staking_module_id).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `getStakingModuleNonce({staking_module_id})`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    def get_staking_module_max_deposits_count(
        self,
        staking_module_id: int,
        depositable_ether: Wei,
        block_identifier: BlockIdentifier = 'latest',
    ) -> int:
        response = self.functions.getStakingModuleMaxDepositsCount(
            staking_module_id,
            depositable_ether,
        ).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `getStakingModuleMaxDepositsCount({staking_module_id}, {depositable_ether})`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response
