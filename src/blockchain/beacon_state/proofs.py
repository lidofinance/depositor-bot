"""Merkle proofs for a validator's existence in the beacon state.

Built with eth-ssz-specs' generalized-index + proof primitives over the vendored fork
containers, so the proof shape follows the fork automatically: a balanced List on Fulu,
a ProgressiveList (variable depth per index) on Gloas. Nothing here hardcodes a depth.

The full proof proven on-chain is ``validators[i] -> state_root -> beacon_block_root``
(the EIP-4788 anchor): a validator-branch (validators[i] up to the state root) followed
by a header-branch (state_root up to the block root).
"""

import ssz
from ssz.gindex import get_branch_indices

# Header layout is fork-invariant across the forks we support; field names match the tuple
# order kept in BeaconStateData.header (slot, proposer_index, parent_root, state_root, body_root).
HeaderTuple = tuple[int, int, bytes, bytes, bytes]


def build_beacon_block_header(spec, header: HeaderTuple):
    """Build the fork's BeaconBlockHeader from the tuple carried in BeaconStateData.header."""
    slot, proposer_index, parent_root, state_root, body_root = header
    return spec.BeaconBlockHeader(
        slot=slot,
        proposer_index=proposer_index,
        parent_root=parent_root,
        state_root=state_root,
        body_root=body_root,
    )


def validator_gindex(spec, validator_index: int) -> int:
    return ssz.get_generalized_index(spec.BeaconState, 'validators', validator_index)


def header_state_root_gindex(spec) -> int:
    return ssz.get_generalized_index(spec.BeaconBlockHeader, 'state_root')


def full_validator_gindex(spec, validator_index: int) -> int:
    """Generalized index of validators[i] relative to the block root (through the header)."""
    return ssz.gindex_concat(header_state_root_gindex(spec), validator_gindex(spec, validator_index))


def validator_leaf(state, validator_index: int) -> bytes:
    return bytes(state.validators[validator_index].hash_tree_root())


def build_validator_proof(spec, state, validator_index: int) -> list[bytes]:
    """Branch from validators[i] up to the state root."""
    gi = validator_gindex(spec, validator_index)
    return [bytes(node) for node in ssz.build_proof(state, gi)]


def build_validator_proofs(spec, state, validator_indices: list[int]) -> dict[int, list[bytes]]:
    """Branches validators[i] -> state_root for many i, sharing subtree computations.

    ssz.build_proof recomputes each sibling subtree from scratch per call; the big upper siblings
    (spanning large runs of the validators list) are identical across validators, so a node_root
    cache shared across candidates computes each such node once instead of once per candidate.
    Byte-for-byte identical to calling build_validator_proof per index — same branch format, just
    without the repeated work (see verify in test_beacon_state_migration).
    """
    node_cache: dict[int, bytes] = {}

    def node(gindex: int) -> bytes:
        cached = node_cache.get(gindex)
        if cached is None:
            cached = bytes(ssz.node_root(state, gindex))
            node_cache[gindex] = cached
        return cached

    return {i: [node(sibling) for sibling in get_branch_indices(validator_gindex(spec, i))] for i in validator_indices}


def build_header_proof(spec, header) -> list[bytes]:
    """Branch from state_root up to the beacon block root."""
    gi = header_state_root_gindex(spec)
    return [bytes(node) for node in ssz.build_proof(header, gi)]


def verify_proof(leaf: bytes, branch: list[bytes], gindex: int, root: bytes) -> bool:
    """Verify a branch against a root at a generalized index (Root wrappers required by the lib)."""
    return ssz.verify_merkle_proof(ssz.Root(leaf), [ssz.Root(node) for node in branch], gindex, ssz.Root(root))
