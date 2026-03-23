"""
Build Merkle proofs and assemble witness data for TopUpGateway.topUp().
"""
import logging
from dataclasses import dataclass
from typing import List

from blockchain.beacon_state.state import (
    BeaconStateData,
    extract_header_proof,
    extract_validator_proof,
)
from blockchain.beacon_state.ssz_types import (
    BeaconBlockHeader,
    STATE_VALIDATORS,
    VALIDATOR_PUBKEY,
    VALIDATOR_EFFECTIVE_BALANCE,
    VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH,
    VALIDATOR_ACTIVATION_EPOCH,
    VALIDATOR_EXIT_EPOCH,
    VALIDATOR_WITHDRAWABLE_EPOCH,
    VALIDATOR_SLASHED,
)
from blockchain.topup.cmv2_strategy import TopUpCandidate
from providers.consensus import ConsensusClient

logger = logging.getLogger(__name__)


@dataclass
class ValidatorWitness:
    proofs: List[bytes]
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
    witnesses: List[ValidatorWitness]
    # parallel arrays matching witnesses order
    validator_indices: List[int]
    key_indices: List[int]
    operator_ids: List[int]
    pending_balances_gwei: List[int]


def build_topup_proofs(
    cl: ConsensusClient,
    beacon_data: BeaconStateData,
    candidates: List[TopUpCandidate],
) -> TopUpProofData:
    """Build proofs for selected candidates using beacon state."""
    # Header for proof: state_root → beacon_block_root
    header_msg = cl.get_block_header(str(beacon_data.slot))
    header = (
        int(header_msg['slot']),
        int(header_msg['proposer_index']),
        bytes.fromhex(header_msg['parent_root'][2:]),
        bytes.fromhex(header_msg['state_root'][2:]),
        bytes.fromhex(header_msg['body_root'][2:]),
    )

    # Verify anchor
    beacon_block_root = BeaconBlockHeader.get_hash_tree_root(header)
    if beacon_block_root != beacon_data.parent_beacon_block_root:
        raise ValueError(
            f'beacon_block_root mismatch: '
            f'computed=0x{beacon_block_root.hex()}, '
            f'expected=0x{beacon_data.parent_beacon_block_root.hex()}'
        )

    header_proof = extract_header_proof(header)
    validators_list = list(beacon_data.state[STATE_VALIDATORS])

    witnesses = []
    validator_indices = []
    key_indices = []
    operator_ids = []
    pending_balances = []

    for c in candidates:
        validator = validators_list[c.validator_index]

        validator_proof = extract_validator_proof(
            beacon_data.state_field_roots, validators_list, c.validator_index,
        )
        full_proof = validator_proof + header_proof

        witnesses.append(ValidatorWitness(
            proofs=full_proof,
            pubkey=bytes(validator[VALIDATOR_PUBKEY]),
            effective_balance=int(validator[VALIDATOR_EFFECTIVE_BALANCE]),
            activation_eligibility_epoch=int(validator[VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH]),
            activation_epoch=int(validator[VALIDATOR_ACTIVATION_EPOCH]),
            exit_epoch=int(validator[VALIDATOR_EXIT_EPOCH]),
            withdrawable_epoch=int(validator[VALIDATOR_WITHDRAWABLE_EPOCH]),
            slashed=bool(validator[VALIDATOR_SLASHED]),
        ))
        validator_indices.append(c.validator_index)
        key_indices.append(c.key_index)
        operator_ids.append(c.operator_id)
        pending_balances.append(c.pending_balance)

    logger.info({"msg": "Built top-up proofs.", "count": len(witnesses), "slot": beacon_data.slot})

    return TopUpProofData(
        child_block_timestamp=beacon_data.timestamp,
        slot=beacon_data.slot,
        proposer_index=int(header_msg['proposer_index']),
        witnesses=witnesses,
        validator_indices=validator_indices,
        key_indices=key_indices,
        operator_ids=operator_ids,
        pending_balances_gwei=pending_balances,
    )
