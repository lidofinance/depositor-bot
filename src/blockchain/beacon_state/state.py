"""
Beacon state loading, data extraction, and proof building.
"""

# pyright: reportTypedDictNotRequiredAccess=false
import logging
from dataclasses import dataclass, field
from typing import NamedTuple

# from typing import TYPE_CHECKING, Any
from blockchain.beacon_state.merkle_tree import (
    MerkleTree,
    build_sparse_list_proof,
    hash_concat,
    verify_merkle_proof_by_index,
)
from blockchain.beacon_state.ssz_types import (
    CONSOLIDATION_TARGET_INDEX,
    HEADER_STATE_ROOT,
    PENDING_DEPOSIT_AMOUNT,
    PENDING_DEPOSIT_PUBKEY,
    STATE_PENDING_CONSOLIDATIONS,
    STATE_PENDING_DEPOSITS,
    STATE_VALIDATORS,
    VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH,
    VALIDATOR_ACTIVATION_EPOCH,
    VALIDATOR_EFFECTIVE_BALANCE,
    VALIDATOR_EXIT_EPOCH,
    VALIDATOR_PUBKEY,
    VALIDATOR_REGISTRY_LIMIT,
    VALIDATOR_SLASHED,
    VALIDATOR_WITHDRAWABLE_EPOCH,
    BeaconBlockHeader,
    BeaconState,
    Validator,
)
from blockchain.typings import Web3
from providers.consensus import ConsensusClient
from ssz import decode  # type: ignore[attr-defined]
from web3.types import BlockData

logger = logging.getLogger(__name__)

VALIDATORS_LIST_DEPTH = VALIDATOR_REGISTRY_LIMIT.bit_length() - 1


class ValidatorFields(NamedTuple):
    """Compact per-validator fields needed for eligibility checks and proof witnesses."""

    pubkey: bytes
    effective_balance: int
    slashed: bool
    activation_eligibility_epoch: int
    activation_epoch: int
    exit_epoch: int
    withdrawable_epoch: int


@dataclass
class BeaconStateData:
    slot: int
    timestamp: int
    parent_beacon_block_root: bytes
    state_root: bytes
    header: tuple[int, int, bytes, bytes, bytes]
    state_field_roots: list[bytes]
    pubkey_to_index: dict[bytes, int]
    pending_deposits: dict[bytes, int]  # pubkey -> total pending gwei
    consolidation_targets: set[int]  # validator indices
    # hash_tree_root for every validator in state; needed to build the validators merkle tree
    validators_roots: list[bytes] = field(default_factory=list)
    # compact fields for validators whose pubkey is in our set (pubkey_to_index.values())
    validators_fields: dict[int, ValidatorFields] = field(default_factory=dict)


def load_beacon_state_data(
    w3: Web3,
    cl: ConsensusClient,
    pubkeys: set[bytes],
) -> BeaconStateData:
    """Load beacon state and extract data needed for filtering and proofs."""
    # Anchor
    block: BlockData = w3.eth.get_block('latest')
    parent_beacon_block_root = bytes(block['parentBeaconBlockRoot'])
    timestamp = block['timestamp']

    # Slot
    root_hex = '0x' + parent_beacon_block_root.hex()
    header_message = cl.get_block_header(root_hex)
    header = (
        int(header_message['slot']),
        int(header_message['proposer_index']),
        bytes.fromhex(header_message['parent_root'][2:]),
        bytes.fromhex(header_message['state_root'][2:]),
        bytes.fromhex(header_message['body_root'][2:]),
    )
    slot = header[0]
    state_root = header[3]
    # State SSZ
    ssz_bytes = cl.get_beacon_state_ssz(int(header_message['slot']))
    state = decode(ssz_bytes, BeaconState)
    del ssz_bytes

    logger.info({'msg': 'Beacon state loaded.', 'slot': slot})

    # Single pass over validators: hash every validator (for the merkle tree)
    # and extract compact fields for validators whose pubkey is in our set.
    pubkey_to_index: dict[bytes, int] = {}
    validators_roots: list[bytes] = []
    validators_fields: dict[int, ValidatorFields] = {}
    for i, v in enumerate(state[STATE_VALIDATORS]):
        validators_roots.append(Validator.get_hash_tree_root(v))
        pubkey = bytes(v[VALIDATOR_PUBKEY])
        if pubkey in pubkeys:
            pubkey_to_index[pubkey] = i
            validators_fields[i] = ValidatorFields(
                pubkey=pubkey,
                effective_balance=int(v[VALIDATOR_EFFECTIVE_BALANCE]),
                slashed=bool(v[VALIDATOR_SLASHED]),
                activation_eligibility_epoch=int(v[VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH]),
                activation_epoch=int(v[VALIDATOR_ACTIVATION_EPOCH]),
                exit_epoch=int(v[VALIDATOR_EXIT_EPOCH]),
                withdrawable_epoch=int(v[VALIDATOR_WITHDRAWABLE_EPOCH]),
            )

    validator_indices = set(pubkey_to_index.values())
    pending_deposits = extract_pending_deposits(state, pubkeys)
    consolidation_targets = extract_consolidation_targets(state, validator_indices)

    # For proofs
    state_field_roots = compute_state_field_roots(state)
    computed_state_root = MerkleTree(state_field_roots).root
    if computed_state_root != state_root:
        raise ValueError(f'state_root mismatch: computed=0x{computed_state_root.hex()}, expected=0x{state_root.hex()}')

    # All data needed from the decoded state has been extracted; drop it.
    del state

    return BeaconStateData(
        slot=slot,
        timestamp=timestamp,
        parent_beacon_block_root=parent_beacon_block_root,
        state_root=state_root,
        header=header,
        state_field_roots=state_field_roots,
        pubkey_to_index=pubkey_to_index,
        pending_deposits=pending_deposits,
        consolidation_targets=consolidation_targets,
        validators_roots=validators_roots,
        validators_fields=validators_fields,
    )


def build_pubkey_to_index(state, pubkeys: set[bytes]) -> dict[bytes, int]:
    """
    Build mapping pubkey -> validator_index for given pubkeys only.
    Index is needed for proof gindex, validator data lookup, and consolidation target check.
    """
    validators = state[STATE_VALIDATORS]
    result: dict[bytes, int] = {}
    for i, v in enumerate(validators):
        pubkey = bytes(v[VALIDATOR_PUBKEY])
        if pubkey in pubkeys:
            result[pubkey] = i
        if len(result) == len(pubkeys):
            break
    return result


def extract_pending_deposits(state, pubkeys: set[bytes]) -> dict[bytes, int]:
    """
    Sum pending deposit amounts for given pubkeys.
    Used for balance check (actual + pending <= 2045.75 ETH)
    and for pendingBalanceGwei param in TopUpGateway.topUp().
    """
    pending_deposits = state[STATE_PENDING_DEPOSITS]
    result: dict[bytes, int] = {}
    for pd in pending_deposits:
        pubkey = bytes(pd[PENDING_DEPOSIT_PUBKEY])
        if pubkey not in pubkeys:
            continue
        amount = int(pd[PENDING_DEPOSIT_AMOUNT])
        result[pubkey] = result.get(pubkey, 0) + amount
    return result


def extract_consolidation_targets(state, validator_indices: set[int]) -> set[int]:
    """
    Find which of given validator_indices are consolidation targets.
    Used in cmv2_strategy to exclude consolidation targets from top-up.
    """
    pending_consolidations = state[STATE_PENDING_CONSOLIDATIONS]
    result: set[int] = set()
    for pc in pending_consolidations:
        target = int(pc[CONSOLIDATION_TARGET_INDEX])
        if target in validator_indices:
            result.add(target)
    return result


def compute_state_field_roots(state) -> list[bytes]:
    """Compute hash_tree_root for each field of BeaconState."""
    field_roots = []
    for i, sedes in enumerate(BeaconState.field_sedes):
        field_value = state[i]
        field_root = sedes.get_hash_tree_root(field_value)
        field_roots.append(field_root)
    return field_roots


def get_validators_hash_tree_roots(validators_list: list) -> list[bytes]:
    validator_chunks = []
    for v in validators_list:
        chunk = Validator.get_hash_tree_root(v)
        validator_chunks.append(chunk)
    return validator_chunks


def extract_validator_proof(
    state_field_roots: list[bytes], validator_index: int, validator_chunks: list[bytes], nodes_cache: dict
) -> list[bytes]:
    """
    Full proof for a validator from BeaconState.
    3 levels:
        1. validator -> validators_data_root (sparse proof, depth 40)
        2. length add
        3. validators field -> state_root (state tree proof)
    """
    # Step 2: validator -> validators_data_root (sparse proof, depth 40)
    validator_proof = build_sparse_list_proof(
        chunks=validator_chunks, index=validator_index, depth=VALIDATORS_LIST_DEPTH, nodes_cache=nodes_cache
    )

    # Step 3: length add
    length_bytes = len(validator_chunks).to_bytes(32, 'little')
    validator_proof.append(length_bytes)

    # Step 4: state tree proof from validators field to state root
    state_tree = MerkleTree(state_field_roots)
    field_proof = state_tree.get_proof(STATE_VALIDATORS)
    validator_proof.extend(field_proof)

    return validator_proof


def verify_validator_proof(
    state_field_roots: list[bytes],
    validator_index: int,
    validator_proof: list[bytes],
    validator_chunks: list[bytes],
    validators_data_root: bytes,
) -> bool:
    """Verify a full validator proof from validator leaf to BeaconState root."""
    expected_length = VALIDATORS_LIST_DEPTH + 1
    if len(validator_proof) < expected_length:
        return False

    validator_root = validator_chunks[validator_index]

    list_proof = validator_proof[:VALIDATORS_LIST_DEPTH]
    if not verify_merkle_proof_by_index(validator_root, list_proof, validator_index, validators_data_root):
        return False

    length_bytes = validator_proof[VALIDATORS_LIST_DEPTH]
    validators_root = hash_concat(validators_data_root, length_bytes)
    if validators_root != state_field_roots[STATE_VALIDATORS]:
        return False

    field_proof = validator_proof[VALIDATORS_LIST_DEPTH + 1 :]
    state_root = MerkleTree(state_field_roots).root
    return verify_merkle_proof_by_index(validators_root, field_proof, STATE_VALIDATORS, state_root)


def extract_header_proof(header) -> list[bytes]:
    """Proof for state_root field in BeaconBlockHeader."""
    field_roots = []
    for i, sedes in enumerate(BeaconBlockHeader.field_sedes):
        field_value = header[i]
        field_root = sedes.get_hash_tree_root(field_value)
        field_roots.append(field_root)

    header_tree = MerkleTree(field_roots)
    return header_tree.get_proof(HEADER_STATE_ROOT)


def verify_header_proof(state_root: bytes, beacon_block_root: bytes, header_proof: list[bytes]) -> bool:
    """Verify the BeaconBlockHeader proof from state_root to beacon_block_root."""
    return verify_merkle_proof_by_index(state_root, header_proof, HEADER_STATE_ROOT, beacon_block_root)
