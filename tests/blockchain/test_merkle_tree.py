import pytest
from blockchain.beacon_state.merkle_tree import (
    MerkleTree,
    build_sparse_list_proof,
    compute_merkle_root_sparse,
    hash_concat,
    verify_merkle_proof_by_index,
)
from blockchain.beacon_state.ssz_types import HEADER_STATE_ROOT, STATE_VALIDATORS, BeaconBlockHeader, Validator
from blockchain.beacon_state.state import VALIDATORS_LIST_DEPTH


@pytest.mark.unit
def test_sparse_validators_root_matches_fixture_state(top_up_proof_fixtures):
    validators_list = list(top_up_proof_fixtures['decoded_beacon_state'][STATE_VALIDATORS])
    validator_chunks = [Validator.get_hash_tree_root(v) for v in validators_list]
    validators_data_root = compute_merkle_root_sparse(validator_chunks, VALIDATORS_LIST_DEPTH)
    length_bytes = len(validators_list).to_bytes(32, 'little')

    # BeaconState.validators root = validators_data_root mixed in with validators list length
    assert top_up_proof_fixtures['beacon_state_field_roots'][STATE_VALIDATORS] == hash_concat(validators_data_root, length_bytes)


@pytest.mark.unit
def test_build_sparse_list_proof_matches_fixture_for_first_validator(top_up_proof_fixtures):
    # fixtures proofs
    validator_witness = top_up_proof_fixtures['validator_witnesses'][0]
    full_proof = [bytes.fromhex(item[2:]) for item in validator_witness['proofs']]
    expected_list_proof = full_proof[:VALIDATORS_LIST_DEPTH]

    # validator -> validators_data_root proofs
    validator_index = int(validator_witness['validatorIndex'])
    validators_list = list(top_up_proof_fixtures['decoded_beacon_state'][STATE_VALIDATORS])
    validator_chunks = [Validator.get_hash_tree_root(v) for v in validators_list]
    actual_list_proof = build_sparse_list_proof(
        chunks=validator_chunks,
        index=validator_index,
        depth=VALIDATORS_LIST_DEPTH,
    )

    assert actual_list_proof == expected_list_proof

    length_bytes = len(validator_chunks).to_bytes(32, 'little')
    actual_list_proof.append(length_bytes)

    assert actual_list_proof == full_proof[: VALIDATORS_LIST_DEPTH + 1]


# [validators _witness][proofs]: validator -> validators_data_root -> validators_root -> beacon_state_root -> beacon_block_root
# [validators _witness][proofs][:VALIDATORS_LIST_DEPTH]:
# part of proofs showing validator exists in BeaconState.validators validator -> validators_data_root
# This test checks that fixture proof segments match proofs rebuilt from:
# - the BeaconState field roots tree
# - the BeaconBlockHeader field roots tree
@pytest.mark.unit
def test_fixture_state_and_header_proofs_match_rebuilt_trees(top_up_proof_fixtures):
    validator_witness = top_up_proof_fixtures['validator_witnesses'][0]
    full_proof = [bytes.fromhex(item[2:]) for item in validator_witness['proofs']]
    state_field_proof = full_proof[VALIDATORS_LIST_DEPTH + 1 : -3]
    header_proof = full_proof[-3:]

    state_tree = MerkleTree(top_up_proof_fixtures['beacon_state_field_roots'])
    assert state_tree.get_proof(STATE_VALIDATORS) == state_field_proof

    header_field_roots = []
    for value, sedes in zip(top_up_proof_fixtures['beacon_block_header'], BeaconBlockHeader.field_sedes):
        header_field_roots.append(sedes.get_hash_tree_root(value))

    header_tree = MerkleTree(header_field_roots)
    assert header_tree.get_proof(HEADER_STATE_ROOT) == header_proof


@pytest.mark.unit
def test_beacon_state_tree_root_matches_beacon_block_header_state_root(top_up_proof_fixtures):
    beacon_state_tree = MerkleTree(top_up_proof_fixtures['beacon_state_field_roots'])
    expected_state_root = top_up_proof_fixtures['beacon_block_header'][HEADER_STATE_ROOT]

    assert beacon_state_tree.root == expected_state_root


@pytest.mark.unit
def test_verify_merkle_proof_by_index_matches_fixture_validator_list_proof(top_up_proof_fixtures):
    validator_witness = top_up_proof_fixtures['validator_witnesses'][0]
    validator_index = int(validator_witness['validatorIndex'])
    full_proof = [bytes.fromhex(item[2:]) for item in validator_witness['proofs']]
    list_proof = full_proof[:VALIDATORS_LIST_DEPTH]

    validators_list = list(top_up_proof_fixtures['decoded_beacon_state'][STATE_VALIDATORS])
    validator_chunks = [Validator.get_hash_tree_root(v) for v in validators_list]
    validator_root = Validator.get_hash_tree_root(validators_list[validator_index])
    validators_data_root = compute_merkle_root_sparse(validator_chunks, VALIDATORS_LIST_DEPTH)

    assert verify_merkle_proof_by_index(
        validator_root,
        list_proof,
        validator_index,
        validators_data_root,
    )


@pytest.mark.unit
def test_verify_merkle_proof_by_index_matches_fixture_validators_root_to_state_root(top_up_proof_fixtures):
    validator_witness = top_up_proof_fixtures['validator_witnesses'][0]
    full_proof = [bytes.fromhex(item[2:]) for item in validator_witness['proofs']]
    state_field_proof = full_proof[VALIDATORS_LIST_DEPTH + 1 : -3]

    validators_list = list(top_up_proof_fixtures['decoded_beacon_state'][STATE_VALIDATORS])
    validator_chunks = [Validator.get_hash_tree_root(v) for v in validators_list]
    validators_data_root = compute_merkle_root_sparse(validator_chunks, VALIDATORS_LIST_DEPTH)
    validators_root = hash_concat(validators_data_root, len(validators_list).to_bytes(32, 'little'))
    state_root = top_up_proof_fixtures['beacon_block_header'][HEADER_STATE_ROOT]

    assert verify_merkle_proof_by_index(
        validators_root,
        state_field_proof,
        STATE_VALIDATORS,
        state_root,
    )


@pytest.mark.unit
def test_verify_merkle_proof_by_index_matches_fixture_validators_root_to_block_header_root(top_up_proof_fixtures):
    validator_witness = top_up_proof_fixtures['validator_witnesses'][0]
    full_proof = [bytes.fromhex(item[2:]) for item in validator_witness['proofs']]
    header_proof = full_proof[-3:]

    beacon_state_tree = MerkleTree(top_up_proof_fixtures['beacon_state_field_roots'])
    header_block_root = bytes.fromhex(top_up_proof_fixtures['execution_block']['parentBeaconBlockRoot'][2:])

    assert verify_merkle_proof_by_index(
        beacon_state_tree.root,
        header_proof,
        HEADER_STATE_ROOT,
        header_block_root,
    )
