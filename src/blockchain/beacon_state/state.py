"""
Beacon state loading and data extraction on the vendored consensus-specs fork types.

The fork is chosen from the slot (see beacon_state.specs.get_spec): Fulu, or Gloas once
GLOAS_PIVOT_SLOT is set. Field access is by name; the eth-ssz-specs value types are strict,
so primitives handed to the rest of the service are unwrapped (bytes(...)/int(...)/bool(...)).
Proof building lives in beacon_state.proofs.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from web3.types import BlockData

from blockchain.beacon_state.specs import get_spec
from blockchain.typings import Web3
from providers.consensus import ConsensusClient

logger = logging.getLogger(__name__)


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
    pubkey_to_index: dict[bytes, int]
    pending_deposits: dict[bytes, int]  # pubkey -> total pending gwei
    consolidation_targets: set[int]  # validator indices
    # compact fields for validators whose pubkey is in our set (pubkey_to_index.values())
    validators_fields: dict[int, ValidatorFields] = field(default_factory=dict)
    # Heavy, pubkey-independent load state, filled only by load_raw_beacon_state and shared by
    # reference into the slices extract_state_data returns. Empty on instances built the old way.
    all_pubkey_to_index: dict[bytes, int] = field(default_factory=dict, repr=False)
    raw_state: Any = field(default=None, repr=False)  # decoded BeaconState, retained for proofs/extract


def _validator_fields(pubkey: bytes, v) -> ValidatorFields:
    return ValidatorFields(
        pubkey=pubkey,
        effective_balance=int(v.effective_balance),
        slashed=bool(v.slashed),
        activation_eligibility_epoch=int(v.activation_eligibility_epoch),
        activation_epoch=int(v.activation_epoch),
        exit_epoch=int(v.exit_epoch),
        withdrawable_epoch=int(v.withdrawable_epoch),
    )


def load_raw_beacon_state(w3: Web3, cl: ConsensusClient) -> BeaconStateData:
    """Read the beacon state and compute everything that does NOT depend on which pubkeys we care
    about: the decoded state, its root self-check, header/anchor and a full pubkey->index map.
    This is the expensive part (SSZ I/O, decode, hashing).

    Do it once per iteration, then slice per module with extract_state_data — so evaluating a second
    module in the same cycle reuses this instead of downloading the state again. The pubkey-specific
    fields are left empty on the returned object; fill them per module with extract_state_data.
    """
    # Anchor
    block: BlockData = w3.eth.get_block('latest')
    parent_beacon_block_root = bytes(block['parentBeaconBlockRoot'])
    timestamp = block['timestamp']

    # Slot / header
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

    spec = get_spec(slot)

    # State SSZ
    ssz_bytes = cl.get_beacon_state_ssz(slot)
    state = spec.BeaconState.decode_bytes(ssz_bytes)
    del ssz_bytes

    # Root self-check: the decoded state must hash to the header's state_root.
    computed_state_root = bytes(state.hash_tree_root())
    if computed_state_root != state_root:
        raise ValueError(f'state_root mismatch: computed=0x{computed_state_root.hex()}, expected=0x{state_root.hex()}')

    logger.info({'msg': 'Beacon state loaded.', 'slot': slot})

    # Single pubkey-independent pass: record each validator's index. Shared across all modules.
    all_pubkey_to_index: dict[bytes, int] = {}
    for i, v in enumerate(state.validators):
        all_pubkey_to_index[bytes(v.pubkey)] = i

    return BeaconStateData(
        slot=slot,
        timestamp=timestamp,
        parent_beacon_block_root=parent_beacon_block_root,
        state_root=state_root,
        header=header,
        pubkey_to_index={},
        pending_deposits={},
        consolidation_targets=set(),
        validators_fields={},
        all_pubkey_to_index=all_pubkey_to_index,
        raw_state=state,
    )


def extract_state_data(raw: BeaconStateData, pubkeys: set[bytes]) -> BeaconStateData:
    """Cheap, pubkey-specific slice of a state already read by load_raw_beacon_state: resolve the
    requested pubkeys to indices/fields and pull their pending deposits and consolidation targets.

    Returns a new BeaconStateData that shares the heavy fields by reference and fills the
    pubkey-specific ones. Safe to call once per module without reloading.
    """
    state = raw.raw_state
    pubkey_to_index: dict[bytes, int] = {}
    validators_fields: dict[int, ValidatorFields] = {}
    for pubkey in pubkeys:
        i = raw.all_pubkey_to_index.get(pubkey)
        if i is None:
            continue
        pubkey_to_index[pubkey] = i
        validators_fields[i] = _validator_fields(pubkey, state.validators[i])

    validator_indices = set(pubkey_to_index.values())
    pending_deposits = extract_pending_deposits(state, pubkeys)
    consolidation_targets = extract_consolidation_targets(state, validator_indices)

    return BeaconStateData(
        slot=raw.slot,
        timestamp=raw.timestamp,
        parent_beacon_block_root=raw.parent_beacon_block_root,
        state_root=raw.state_root,
        header=raw.header,
        pubkey_to_index=pubkey_to_index,
        pending_deposits=pending_deposits,
        consolidation_targets=consolidation_targets,
        validators_fields=validators_fields,
        all_pubkey_to_index=raw.all_pubkey_to_index,
        raw_state=state,
    )


def build_pubkey_to_index(state, pubkeys: set[bytes]) -> dict[bytes, int]:
    """Build mapping pubkey -> validator_index for given pubkeys only."""
    result: dict[bytes, int] = {}
    for i, v in enumerate(state.validators):
        pubkey = bytes(v.pubkey)
        if pubkey in pubkeys:
            result[pubkey] = i
        if len(result) == len(pubkeys):
            break
    return result


def extract_pending_deposits(state, pubkeys: set[bytes]) -> dict[bytes, int]:
    """Sum pending deposit amounts for given pubkeys (for the balance check and pendingBalanceGwei)."""
    result: dict[bytes, int] = {}
    for pd in state.pending_deposits:
        pubkey = bytes(pd.pubkey)
        if pubkey not in pubkeys:
            continue
        result[pubkey] = result.get(pubkey, 0) + int(pd.amount)
    return result


def extract_consolidation_targets(state, validator_indices: set[int]) -> set[int]:
    """Find which of given validator_indices are consolidation targets (excluded from top-up)."""
    result: set[int] = set()
    for pc in state.pending_consolidations:
        target = int(pc.target_index)
        if target in validator_indices:
            result.add(target)
    return result
