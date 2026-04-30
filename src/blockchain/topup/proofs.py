"""
Build Merkle proofs and assemble witness data for TopUpGateway.topUp().
"""

import logging

from blockchain.beacon_state.ssz_types import BeaconBlockHeader
from blockchain.beacon_state.state import (
    BeaconStateData,
    extract_header_proof,
    extract_validator_proof,
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

    # if not verify_header_proof(state_root, beacon_block_root, header_proof):
    #     raise ValueError(f'Invalid header proof for slot={beacon_data.slot}')

    witnesses = []
    validator_indices = []
    key_indices = []
    operator_ids = []
    pending_balances = []

    validators_roots = beacon_data.validators_roots
    nodes_cache: dict = {}

    for c in candidates:
        fields = beacon_data.validators_fields[c.validator_index]

        validator_proof = extract_validator_proof(beacon_data.state_field_roots, c.validator_index, validators_roots, nodes_cache)
        # if not verify_validator_proof(
        #     beacon_data.state_field_roots,
        #     c.validator_index,
        #     validator_proof,
        #     validators_roots,
        #     validators_data_root,
        # ):
        #     raise ValueError(f'Invalid validator proof for validator_index={c.validator_index}')

        full_proof = validator_proof + header_proof

        witnesses.append(
            ValidatorWitness(
                proofs=full_proof,
                pubkey=fields.pubkey,
                effective_balance=fields.effective_balance,
                activation_eligibility_epoch=fields.activation_eligibility_epoch,
                activation_epoch=fields.activation_epoch,
                exit_epoch=fields.exit_epoch,
                withdrawable_epoch=fields.withdrawable_epoch,
                slashed=fields.slashed,
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
