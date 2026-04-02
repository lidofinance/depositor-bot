from unittest.mock import MagicMock

import pytest
from blockchain.beacon_state.merkle_tree import (
    MerkleTree,
    compute_merkle_root_sparse,
    hash_concat,
    verify_merkle_proof_by_index,
)
from blockchain.beacon_state.ssz_types import (
    CONSOLIDATION_TARGET_INDEX,
    PENDING_DEPOSIT_AMOUNT,
    PENDING_DEPOSIT_PUBKEY,
    STATE_PENDING_CONSOLIDATIONS,
    STATE_PENDING_DEPOSITS,
    STATE_VALIDATORS,
    VALIDATOR_PUBKEY,
    BeaconBlockHeader,
    BeaconState,
    Validator,
)
from blockchain.beacon_state.state import (
    VALIDATORS_LIST_DEPTH,
    build_pubkey_to_index,
    compute_state_field_roots,
    extract_consolidation_targets,
    extract_header_proof,
    extract_pending_deposits,
    extract_validator_proof,
    get_validators_hash_tree_roots,
    load_beacon_state_data,
    verify_header_proof,
    verify_validator_proof,
)


def _bytes32(seed: int) -> bytes:
    return seed.to_bytes(32, 'little')


def _validator(seed: int) -> tuple[bytes, bytes, int, bool, int, int, int, int]:
    return (
        seed.to_bytes(48, 'little'),
        _bytes32(seed + 1000),
        32_000_000_000 + seed,
        bool(seed % 2),
        seed,
        seed + 1,
        seed + 2,
        seed + 3,
    )


def _flip_first_bit(chunk: bytes) -> bytes:
    return bytes([chunk[0] ^ 1]) + chunk[1:]


@pytest.mark.unit
def test_verify_merkle_proof_by_index_roundtrip():
    leaves = [_bytes32(i) for i in range(4)]
    tree = MerkleTree(leaves)
    proof = tree.get_proof(2)

    assert verify_merkle_proof_by_index(leaves[2], proof, 2, tree.root)
    assert not verify_merkle_proof_by_index(_flip_first_bit(leaves[2]), proof, 2, tree.root)


@pytest.mark.unit
def test_verify_validator_and_header_proofs():
    validators_list = [_validator(i) for i in range(3)]
    validator_chunks = [Validator.get_hash_tree_root(v) for v in validators_list]
    validators_data_root = compute_merkle_root_sparse(validator_chunks, VALIDATORS_LIST_DEPTH)
    state_field_roots = [_bytes32(10_000 + i) for i in range(len(BeaconState.field_sedes))]
    state_field_roots[STATE_VALIDATORS] = hash_concat(validators_data_root, len(validators_list).to_bytes(32, 'little'))
    state_root = MerkleTree(state_field_roots).root

    header = (
        123,
        456,
        _bytes32(20_000),
        state_root,
        _bytes32(20_001),
    )
    beacon_block_root = BeaconBlockHeader.get_hash_tree_root(header)

    nodes_cache: dict = {}
    validator_proof = extract_validator_proof(state_field_roots, 1, validator_chunks, nodes_cache)
    header_proof = extract_header_proof(header)

    assert verify_validator_proof(state_field_roots, 1, validator_proof, validator_chunks, validators_data_root)
    assert verify_header_proof(state_root, beacon_block_root, header_proof)

    broken_validator_proof = list(validator_proof)
    broken_validator_proof[0] = _flip_first_bit(broken_validator_proof[0])
    assert not verify_validator_proof(state_field_roots, 1, broken_validator_proof, validator_chunks, validators_data_root)

    broken_header_proof = list(header_proof)
    broken_header_proof[0] = _flip_first_bit(broken_header_proof[0])
    assert not verify_header_proof(state_root, beacon_block_root, broken_header_proof)


@pytest.mark.unit
def test_load_beacon_state_data_matches_fixture(top_up_proof_fixtures):
    beacon_block_header = top_up_proof_fixtures['beacon_block_header']
    execution_block = top_up_proof_fixtures['execution_block']
    pubkeys = {bytes.fromhex(w['pubkey'][2:]) for w in top_up_proof_fixtures['validator_witnesses']}

    w3 = MagicMock()
    w3.eth.get_block.return_value = {
        'parentBeaconBlockRoot': bytes.fromhex(execution_block['parentBeaconBlockRoot'][2:]),
        'timestamp': execution_block['timestamp'],
    }

    cl = MagicMock()
    cl.get_block_header.return_value = {
        'slot': str(beacon_block_header[0]),
        'proposer_index': str(beacon_block_header[1]),
        'parent_root': '0x' + beacon_block_header[2].hex(),
        'state_root': '0x' + beacon_block_header[3].hex(),
        'body_root': '0x' + beacon_block_header[4].hex(),
    }
    cl.get_beacon_state_ssz.return_value = top_up_proof_fixtures['beacon_state_ssz']

    result = load_beacon_state_data(w3, cl, pubkeys)

    assert result.slot == beacon_block_header[0]
    assert result.timestamp == execution_block['timestamp']
    assert result.parent_beacon_block_root == bytes.fromhex(execution_block['parentBeaconBlockRoot'][2:])
    assert result.state_root == beacon_block_header[3]
    assert result.header == beacon_block_header
    assert result.pubkey_to_index == build_pubkey_to_index(top_up_proof_fixtures['decoded_beacon_state'], pubkeys)
    assert result.pending_deposits == extract_pending_deposits(top_up_proof_fixtures['decoded_beacon_state'], pubkeys)
    assert result.consolidation_targets == extract_consolidation_targets(
        top_up_proof_fixtures['decoded_beacon_state'],
        set(result.pubkey_to_index.values()),
    )
    assert result.state_field_roots == top_up_proof_fixtures['beacon_state_field_roots']


@pytest.mark.unit
def test_state_helpers_match_fixture_state(top_up_proof_fixtures):
    state = top_up_proof_fixtures['decoded_beacon_state']
    pubkeys = {bytes.fromhex(w['pubkey'][2:]) for w in top_up_proof_fixtures['validator_witnesses']}

    expected_pubkey_to_index = {}
    for index, validator in enumerate(state[STATE_VALIDATORS]):
        pubkey = bytes(validator[VALIDATOR_PUBKEY])
        if pubkey in pubkeys:
            expected_pubkey_to_index[pubkey] = index

    expected_pending_deposits = {}
    for pending_deposit in state[STATE_PENDING_DEPOSITS]:
        pubkey = bytes(pending_deposit[PENDING_DEPOSIT_PUBKEY])
        if pubkey in pubkeys:
            expected_pending_deposits[pubkey] = expected_pending_deposits.get(pubkey, 0) + int(pending_deposit[PENDING_DEPOSIT_AMOUNT])

    validator_indices = set(expected_pubkey_to_index.values())
    expected_consolidation_targets = {
        int(consolidation[CONSOLIDATION_TARGET_INDEX])
        for consolidation in state[STATE_PENDING_CONSOLIDATIONS]
        if int(consolidation[CONSOLIDATION_TARGET_INDEX]) in validator_indices
    }

    assert build_pubkey_to_index(state, pubkeys) == expected_pubkey_to_index
    assert extract_pending_deposits(state, pubkeys) == expected_pending_deposits
    assert extract_consolidation_targets(state, validator_indices) == expected_consolidation_targets
    assert compute_state_field_roots(state) == top_up_proof_fixtures['beacon_state_field_roots']


@pytest.mark.unit
def test_extract_validator_proof_matches_fixture_for_first_validator(top_up_proof_fixtures):
    validator_witness = top_up_proof_fixtures['validator_witnesses'][0]
    validator_index = int(validator_witness['validatorIndex'])
    expected_validator_proof = [bytes.fromhex(item[2:]) for item in validator_witness['proofs'][:-3]]
    validators_list = list(top_up_proof_fixtures['decoded_beacon_state'][STATE_VALIDATORS])

    validator_chunks = get_validators_hash_tree_roots(validators_list)
    validators_data_root = compute_merkle_root_sparse(validator_chunks, VALIDATORS_LIST_DEPTH)
    nodes_cache: dict = {}

    validator_proof = extract_validator_proof(
        top_up_proof_fixtures['beacon_state_field_roots'],
        validator_index,
        validator_chunks,
        nodes_cache,
    )

    assert validator_proof == expected_validator_proof
    assert verify_validator_proof(
        top_up_proof_fixtures['beacon_state_field_roots'],
        validator_index,
        validator_proof,
        validator_chunks,
        validators_data_root,
    )


@pytest.mark.unit
def test_extract_header_proof_matches_fixture_header_tail(top_up_proof_fixtures):
    validator_witness = top_up_proof_fixtures['validator_witnesses'][0]
    expected_header_proof = [bytes.fromhex(item[2:]) for item in validator_witness['proofs'][-3:]]
    beacon_block_header = top_up_proof_fixtures['beacon_block_header']
    beacon_block_root = BeaconBlockHeader.get_hash_tree_root(beacon_block_header)

    header_proof = extract_header_proof(beacon_block_header)

    assert header_proof == expected_header_proof
    assert verify_header_proof(beacon_block_header[3], beacon_block_root, header_proof)
