# pyright: reportTypedDictNotRequiredAccess=false
"""
Beacon state loading, data extraction, and proof building.
"""

import logging
from dataclasses import dataclass
from typing import Any, List

from ssz import decode  # type: ignore[attr-defined]

from blockchain.beacon_state.merkle_tree import MerkleTree, hash_concat
from blockchain.beacon_state.ssz_types import (
    BeaconBlockHeader,
    BeaconState,
    Validator,
    STATE_VALIDATORS,
    STATE_BALANCES,
    STATE_PENDING_DEPOSITS,
    STATE_PENDING_CONSOLIDATIONS,
    VALIDATOR_PUBKEY,
    PENDING_DEPOSIT_PUBKEY,
    PENDING_DEPOSIT_AMOUNT,
    CONSOLIDATION_TARGET_INDEX,
)
from blockchain.typings import Web3
from providers.consensus import ConsensusClient
from web3.types import BlockData

logger = logging.getLogger(__name__)


@dataclass
class BeaconStateData:
    slot: int
    timestamp: int
    parent_beacon_block_root: bytes
    state: Any  # decoded SSZ BeaconState, kept for proofs
    state_field_roots: list[bytes]
    pubkey_to_index: dict[bytes, int]
    pending_deposits: dict[bytes, int]  # pubkey -> total pending gwei
    consolidation_targets: set[int]  # validator indices


def load_beacon_state_data(
    w3: Web3, cl: ConsensusClient, pubkeys: set[bytes]
) -> BeaconStateData:
    """Load beacon state and extract data needed for filtering and proofs."""
    # Anchor
    block: BlockData = w3.eth.get_block("latest")
    parent_beacon_block_root = bytes(block["parentBeaconBlockRoot"])
    timestamp = block["timestamp"]

    # Slot
    root_hex = "0x" + parent_beacon_block_root.hex()
    message = cl.get_block_details(root_hex)
    slot = int(message["slot"])

    # State SSZ
    ssz_bytes = cl.get_beacon_state_ssz(slot)
    state = decode(ssz_bytes, BeaconState)
    del ssz_bytes

    logger.info({"msg": "Beacon state loaded.", "slot": slot})

    # Extract data for our pubkeys
    pubkey_to_index = build_pubkey_to_index(state, pubkeys)
    validator_indices = set(pubkey_to_index.values())
    pending_deposits = extract_pending_deposits(state, pubkeys)
    consolidation_targets = extract_consolidation_targets(state, validator_indices)

    # For proofs
    state_field_roots = compute_state_field_roots(state)

    return BeaconStateData(
        slot=slot,
        timestamp=timestamp,
        parent_beacon_block_root=parent_beacon_block_root,
        state=state,
        state_field_roots=state_field_roots,
        pubkey_to_index=pubkey_to_index,
        pending_deposits=pending_deposits,
        consolidation_targets=consolidation_targets,
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


def compute_state_field_roots(state) -> List[bytes]:
    """Compute hash_tree_root for each field of BeaconState."""
    field_roots = []
    for i, sedes in enumerate(BeaconState.field_sedes):
        field_value = state[i]
        field_root = sedes.get_hash_tree_root(field_value)
        field_roots.append(field_root)
    return field_roots


def extract_validator_proof(
    state_field_roots: List[bytes],
    validators_list: list,
    validator_index: int,
) -> List[bytes]:
    """
    Full proof for a validator from BeaconState.
    3 levels:
        1. validator -> validators_data_root (sparse proof, depth 40)
        2. length mixin
        3. validators field -> state_root (state tree proof)
    """
    VALIDATORS_FIELD_INDEX = 11
    VALIDATORS_LIST_DEPTH = 40

    # Step 1: compute validator chunks
    validator_chunks = []
    for v in validators_list:
        chunk = Validator.get_hash_tree_root(v)
        validator_chunks.append(chunk)

    # Step 2: sparse proof from validator to list data root
    tree = MerkleTree([], None)
    validator_proof = tree.build_sparse_list_proof(
        chunks=validator_chunks,
        index=validator_index,
        depth=VALIDATORS_LIST_DEPTH,
    )

    # Step 3: length add
    length_bytes = len(validators_list).to_bytes(32, "little")
    validator_proof.append(length_bytes)

    # Step 4: state tree proof from validators field to state root
    state_tree = MerkleTree(state_field_roots)
    field_proof = state_tree.get_proof(VALIDATORS_FIELD_INDEX)
    validator_proof.extend(field_proof)

    return validator_proof


def extract_header_proof(header) -> List[bytes]:
    """Proof for state_root field in BeaconBlockHeader."""
    STATE_ROOT_INDEX = 3

    field_roots = []
    for i, sedes in enumerate(BeaconBlockHeader.field_sedes):
        field_value = header[i]
        field_root = sedes.get_hash_tree_root(field_value)
        field_roots.append(field_root)

    header_tree = MerkleTree(field_roots)
    return header_tree.get_proof(STATE_ROOT_INDEX)
