"""
Build Merkle proofs and assemble witness data for TopUpGateway.topUp().
"""

import logging

from blockchain.beacon_state.ssz_types import (
    STATE_VALIDATORS,
    VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH,
    VALIDATOR_ACTIVATION_EPOCH,
    VALIDATOR_EFFECTIVE_BALANCE,
    VALIDATOR_EXIT_EPOCH,
    VALIDATOR_PUBKEY,
    VALIDATOR_SLASHED,
    VALIDATOR_WITHDRAWABLE_EPOCH,
    BeaconBlockHeader,
)
from blockchain.beacon_state.state import (
    BeaconStateData,
    extract_header_proof,
    extract_validator_proof,
    verify_header_proof,
    verify_validator_proof,
)
from blockchain.topup.types import TopUpCandidate, TopUpProofData, ValidatorWitness

logger = logging.getLogger(__name__)


def build_topup_proofs(
    beacon_data: BeaconStateData,
    candidates: list[TopUpCandidate],
) -> TopUpProofData:
    """Build proofs for selected candidates using beacon state."""
    # Header for proof: state_root → beacon_block_root

    header = beacon_data.header

    # Verify anchor
    beacon_block_root = BeaconBlockHeader.get_hash_tree_root(header)
    if beacon_block_root != beacon_data.parent_beacon_block_root:
        raise ValueError(
            f'beacon_block_root mismatch: '
            f'computed=0x{beacon_block_root.hex()}, '
            f'expected=0x{beacon_data.parent_beacon_block_root.hex()}'
        )

    header_proof = extract_header_proof(header)
    state_root = header[3]
    if state_root != beacon_data.state_root:
        raise ValueError(f'header/state root mismatch: header=0x{state_root.hex()}, beacon_data=0x{beacon_data.state_root.hex()}')

    if not verify_header_proof(state_root, beacon_block_root, header_proof):
        raise ValueError(f'Invalid header proof for slot={beacon_data.slot}')
    validators_list = list(beacon_data.state[STATE_VALIDATORS])

    witnesses = []
    validator_indices = []
    key_indices = []
    operator_ids = []
    pending_balances = []

    for c in candidates:
        validator = validators_list[c.validator_index]

        validator_proof = extract_validator_proof(
            beacon_data.state_field_roots,
            validators_list,
            c.validator_index,
        )
        if not verify_validator_proof(
            beacon_data.state_field_roots,
            validators_list,
            c.validator_index,
            validator_proof,
        ):
            raise ValueError(f'Invalid validator proof for validator_index={c.validator_index}')

        full_proof = validator_proof + header_proof

        witnesses.append(
            ValidatorWitness(
                proofs=full_proof,
                pubkey=bytes(validator[VALIDATOR_PUBKEY]),
                effective_balance=int(validator[VALIDATOR_EFFECTIVE_BALANCE]),
                activation_eligibility_epoch=int(validator[VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH]),
                activation_epoch=int(validator[VALIDATOR_ACTIVATION_EPOCH]),
                exit_epoch=int(validator[VALIDATOR_EXIT_EPOCH]),
                withdrawable_epoch=int(validator[VALIDATOR_WITHDRAWABLE_EPOCH]),
                slashed=bool(validator[VALIDATOR_SLASHED]),
            )
        )
        validator_indices.append(c.validator_index)
        key_indices.append(c.key_index)
        operator_ids.append(c.operator_id)
        pending_balances.append(c.pending_balance)

    logger.info({'msg': 'Built top-up proofs.', 'count': len(witnesses), 'slot': beacon_data.slot})

    return TopUpProofData(
        child_block_timestamp=beacon_data.timestamp,
        slot=beacon_data.slot,
        proposer_index=header[1],
        witnesses=witnesses,
        validator_indices=validator_indices,
        key_indices=key_indices,
        operator_ids=operator_ids,
        pending_balances_gwei=pending_balances,
    )
