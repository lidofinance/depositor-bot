from dataclasses import dataclass


@dataclass
class TopUpCandidate:
    validator_index: int
    key_index: int
    operator_id: int
    pubkey: bytes
    pending_balance: int  # gwei


@dataclass
class ValidatorWitness:
    proofs: list[bytes]
    pubkey: bytes
    effective_balance: int
    activation_eligibility_epoch: int
    activation_epoch: int
    exit_epoch: int
    withdrawable_epoch: int
    slashed: bool


@dataclass
class TopUpProofData:
    """Ready for TopUpGateway.topUp() call."""

    child_block_timestamp: int
    slot: int
    proposer_index: int
    witnesses: list[ValidatorWitness]
    validator_indices: list[int]
    key_indices: list[int]
    operator_ids: list[int]
    pending_balances_gwei: list[int]
