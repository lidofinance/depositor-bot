import logging

from web3.types import Wei, BlockIdentifier

from blockchain.contracts.base_interface import ContractInterface


logger = logging.getLogger(__name__)


class StakingRouterContract(ContractInterface):
    abi_path = './interfaces/StakingRouter.json'

    def get_staking_module_ids(self, block_identifier: BlockIdentifier = 'latest') -> list[int]:
        """Returns the ids of all registered staking modules"""
        response = self.functions.getStakingModuleIds().call(block_identifier=block_identifier)
        logger.info({
            'msg': f'Call `get_staking_module_ids()`.',
            'value': response,
            'block_identifier': block_identifier.__repr__(),
        })
        return response

    def is_staking_module_active(
        self,
        staking_module_id: int,
        block_identifier: BlockIdentifier = 'latest',
    ) -> bool:
        response = self.functions.getStakingModuleIsActive(staking_module_id).call(block_identifier=block_identifier)
        logger.info({
            'msg': f'Call `getStakingModuleIsActive({staking_module_id})`.',
            'value': response,
            'block_identifier': block_identifier.__repr__(),
        })
        return response

    def get_staking_module_nonce(
        self,
        staking_module_id: int,
        block_identifier: BlockIdentifier = 'latest',
    ) -> int:
        response = self.functions.getStakingModuleNonce(staking_module_id).call(block_identifier=block_identifier)
        logger.info({
            'msg': f'Call `getStakingModuleNonce({staking_module_id})`.',
            'value': response,
            'block_identifier': block_identifier.__repr__(),
        })
        return response

    def get_staking_module_deposits_count(
        self,
        staking_module_id: int,
        depositable_ether: Wei,
        block_identifier: BlockIdentifier = 'latest',
    ) -> int:
        response = self.functions.getStakingModuleMaxDepositsCount(
            staking_module_id,
            depositable_ether,
        ).call(block_identifier=block_identifier)
        logger.info({
            'msg': f'Call `getStakingModuleMaxDepositsCount({staking_module_id}, {depositable_ether})`.',
            'value': response,
            'block_identifier': block_identifier.__repr__(),
        })
        return response
