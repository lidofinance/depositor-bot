import logging
from functools import lru_cache
from typing import TypedDict

from web3.types import BlockIdentifier, Wei

from blockchain.contracts.base_interface import ContractInterface

logger = logging.getLogger(__name__)

MODULE_TYPE_CMV2 = b'curated-onchain-v2'.ljust(32, b'\x00')
MODULE_TYPE_CSM = b'community-onchain-v1'.ljust(32, b'\x00')

# withdrawalCredentialsType of a staking module (StakingModuleDigest field 13)
WC_TYPE_0X01 = 1
WC_TYPE_0X02 = 2


class StakingModuleInfo(TypedDict):
    """Parsed fields from a StakingModuleDigest tuple returned by StakingRouter."""

    module_id: int
    address: str
    wc_type: int
    status: int  # StakingModuleStatus: 0=Active, 1=DepositsPaused, 2=Stopped


class StakingRouterContractV4(ContractInterface):
    abi_path = './interfaces/StakingRouterV4.json'

    @lru_cache(maxsize=1)
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

    @lru_cache(maxsize=1)
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

    def get_all_staking_module_digests(self, block_identifier: BlockIdentifier = 'latest') -> list[StakingModuleInfo]:
        """V4 state tuple includes wc_type at index 13."""
        response = self.functions.getAllStakingModuleDigests().call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': 'Call getAllStakingModuleDigests().',
                'value': response,
                'block_identifier': block_identifier.__repr__(),
            }
        )
        return [StakingModuleInfo(module_id=d[2][0], address=d[2][1], wc_type=d[2][13], status=d[2][5]) for d in response]

    def get_deposit_allocations(
        self,
        deposit_amount: Wei,
        is_top_up: bool,
        block_identifier: BlockIdentifier = 'latest',
    ) -> tuple:
        """Returns deposit allocations across modules.

        Returns:
            (totalAllocated, allocated[], newAllocations[])
        """
        response = self.functions.getDepositAllocations(
            deposit_amount,
            is_top_up,
        ).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `getDepositAllocations({deposit_amount}, {is_top_up})`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    def get_max_top_up_per_block_gwei(self, block_identifier: BlockIdentifier = 'latest') -> int:
        """Global per-block top-up cap (LIP-35). `topUp` funds a module at most
        min(module allocation, this) per call; `getDepositAllocations` does NOT apply it.
        Not cached — it can change via `setMaxTopUpPerBlockGwei`."""
        response = self.functions.getMaxTopUpPerBlockGwei().call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': 'Call `getMaxTopUpPerBlockGwei()`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response
