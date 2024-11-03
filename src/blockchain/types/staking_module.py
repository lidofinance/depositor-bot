from enum import Enum

from blockchain.types.abi import BaseModel
from eth_typing import ChecksumAddress


class StakingModuleStatus(Enum):
    # https://github.com/lidofinance/core/blob/aada42242e893ea2726e629c135cd375d30575fc/contracts/0.8.9/StakingRouter.sol#L63
    Active = 0  # deposits and rewards allowed
    DepositsPaused = 1  # deposits NOT allowed, rewards allowed
    Stopped = 2  # deposits and rewards NOT allowed


class StakingModuleState(BaseModel):
    id: int
    staking_module_address: ChecksumAddress
    staking_module_fee: int
    treasury_fee: int
    stake_share_limit: int
    status: StakingModuleStatus
    name: str
    last_deposit_at: int
    last_deposit_block: int
    exited_validators_count: int
    priority_exit_share_threshold: int
    max_deposits_per_block: int
    min_deposit_block_distance: int


class StakingModuleSummary(BaseModel):
    total_exited_validators: int
    total_deposited_validators: int
    depositable_validators_count: int


class StakingModuleDigest(BaseModel):
    node_operators_count: int
    active_node_operators_count: int
    state: StakingModuleState
    summary: StakingModuleSummary
