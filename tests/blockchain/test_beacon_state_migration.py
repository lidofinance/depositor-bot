"""Migration acceptance tests for the eth-ssz-specs proof path (Fulu + Gloas)."""

import json
from pathlib import Path

import pytest
import ssz

from blockchain.beacon_state.constants import FAR_FUTURE_SLOT, GLOAS_PIVOT_SLOT
from blockchain.beacon_state.proofs import (
    build_beacon_block_header,
    build_header_proof,
    build_validator_proof,
    build_validator_proofs,
    full_validator_gindex,
    validator_gindex,
    validator_leaf,
    verify_proof,
)
from blockchain.beacon_state.specs import fulu, get_spec, gloas

_REF = json.loads((Path(__file__).resolve().parents[1] / 'fixtures' / 'data' / 'top_up_proof' / 'reference_vectors.json').read_text())


@pytest.mark.unit
def test_validators_generalized_indices():
    # BeaconState is a balanced Container on Fulu (validators at field 11 -> gindex 75) and a
    # ProgressiveContainer on Gloas (validators -> gindex 358). Pinning these guards the vendored
    # types: if a regeneration changed the layout, the on-chain GI_VALIDATORS would no longer match.
    assert ssz.get_generalized_index(fulu.BeaconState, 'validators') == 75
    assert ssz.get_generalized_index(gloas.BeaconState, 'validators') == 358


@pytest.mark.unit
def test_fork_selector():
    assert get_spec(GLOAS_PIVOT_SLOT - 1) is fulu
    assert get_spec(GLOAS_PIVOT_SLOT) is gloas  # boundary is inclusive
    # With the default pivot (env GLOAS_PIVOT_SLOT unset) it is "never", so any real slot stays on Fulu.
    if GLOAS_PIVOT_SLOT == FAR_FUTURE_SLOT:
        assert get_spec(15_000_000) is fulu


@pytest.mark.unit
def test_fulu_proof_matches_reference_vectors(top_up_proof_fixtures):
    # Cross-check: the new code reproduces the pre-migration (py-ssz / devnet) proofs byte-for-byte.
    state = top_up_proof_fixtures['decoded_beacon_state']
    header = top_up_proof_fixtures['beacon_block_header']

    block_header = build_beacon_block_header(fulu, header)
    block_root = bytes(block_header.hash_tree_root())
    assert '0x' + block_root.hex() == _REF['block_root']
    assert '0x' + bytes(state.hash_tree_root()).hex() == _REF['state_root']

    header_proof = build_header_proof(fulu, block_header)
    for vec in _REF['vectors']:
        idx = vec['validator_index']
        full_branch = build_validator_proof(fulu, state, idx) + header_proof
        leaf = validator_leaf(state, idx)

        assert '0x' + leaf.hex() == vec['leaf']
        assert ['0x' + b.hex() for b in full_branch] == vec['branch']  # byte-for-byte
        assert verify_proof(leaf, full_branch, full_validator_gindex(fulu, idx), block_root)


@pytest.mark.unit
def test_batched_validator_proofs_match_per_index(top_up_proof_fixtures):
    # The shared-cache batch path must be byte-for-byte identical to per-index build_validator_proof.
    state = top_up_proof_fixtures['decoded_beacon_state']
    n = len(state.validators)
    # A mix of clustered and spread indices to exercise shared and distinct siblings.
    indices = [0, 1, 2, 3, n // 2, n // 2 + 1, n - 2, n - 1]

    batched = build_validator_proofs(fulu, state, indices)
    for i in indices:
        assert batched[i] == build_validator_proof(fulu, state, i)


def _gloas_state(n: int):
    """A minimal Gloas BeaconState with n validators; every other field keeps its default."""
    vals = [
        gloas.Validator(
            pubkey=bytes([i % 256]) * 48,
            withdrawal_credentials=b'\x00' * 32,
            effective_balance=32_000_000_000 + i,
            slashed=bool(i % 2),
            activation_eligibility_epoch=i,
            activation_epoch=i + 1,
            exit_epoch=FAR_FUTURE_SLOT,
            withdrawable_epoch=FAR_FUTURE_SLOT,
        )
        for i in range(n)
    ]
    return gloas.BeaconState(validators=gloas.Validators(data=vals))


@pytest.mark.unit
@pytest.mark.parametrize('idx', [0, 1, 3, 6])
def test_gloas_progressive_roundtrip(idx):
    # Exercises the ProgressiveList path: depth varies per index and nothing hardcodes it.
    state = _gloas_state(7)

    # decode roundtrip
    restored = gloas.BeaconState.decode_bytes(state.encode_bytes())
    assert bytes(restored.hash_tree_root()) == bytes(state.hash_tree_root())

    state_root = bytes(state.hash_tree_root())
    gi = validator_gindex(gloas, idx)
    branch = build_validator_proof(gloas, state, idx)
    leaf = validator_leaf(state, idx)

    assert verify_proof(leaf, branch, gi, state_root)
    tampered = bytes([leaf[0] ^ 1]) + leaf[1:]
    assert not verify_proof(tampered, branch, gi, state_root)
