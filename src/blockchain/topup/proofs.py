"""
Build Merkle proofs and assemble witness data for TopUpGateway.topUp().
"""

import logging

from blockchain.beacon_state.proofs import (
    build_beacon_block_header,
    build_header_proof,
    build_validator_proofs,
    full_validator_gindex,
    validator_leaf,
    verify_proof,
)
from blockchain.beacon_state.specs import get_spec
from blockchain.topup.types import TopUpCandidate, TopUpProofData, ValidatorWitness

logger = logging.getLogger(__name__)


def build_topup_proofs(
    beacon_data,
    candidates: list[TopUpCandidate],
) -> TopUpProofData:
    """Build proofs for selected candidates from the decoded beacon state.

    Each witness proof is validators[i] -> state_root -> beacon_block_root (EIP-4788 anchor).
    """
    spec = get_spec(beacon_data.slot)
    state = beacon_data.raw_state
    header = beacon_data.header

    # Verify anchor: the built block root must match the EIP-4788 parent root.
    block_header = build_beacon_block_header(spec, header)
    beacon_block_root = bytes(block_header.hash_tree_root())
    if beacon_block_root != beacon_data.parent_beacon_block_root:
        raise ValueError(
            f'beacon_block_root mismatch: computed=0x{beacon_block_root.hex()}, expected=0x{beacon_data.parent_beacon_block_root.hex()}'
        )

    state_root = header[3]
    if state_root != beacon_data.state_root:
        raise ValueError(f'header/state root mismatch: header=0x{state_root.hex()}, beacon_data=0x{beacon_data.state_root.hex()}')

    header_proof = build_header_proof(spec, block_header)

    # Build every validator branch in one pass with a shared node cache: the big upper siblings
    # (large spans of the validators list) repeat across candidates and are computed once, not once
    # per candidate. Byte-for-byte identical to per-candidate build_validator_proof.
    validator_proofs = build_validator_proofs(spec, state, [c.validator_index for c in candidates])

    witnesses = []
    validator_indices = []
    key_indices = []
    operator_ids = []
    pending_balances = []

    for c in candidates:
        fields = beacon_data.validators_fields[c.validator_index]

        full_proof = validator_proofs[c.validator_index] + header_proof

        leaf = validator_leaf(state, c.validator_index)
        full_gi = full_validator_gindex(spec, c.validator_index)
        if not verify_proof(leaf, full_proof, full_gi, beacon_block_root):
            raise ValueError(f'Invalid validator proof for validator_index={c.validator_index}')

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
