import pytest
from blockchain.beacon_state.ssz_types import (
    STATE_VALIDATORS,
    VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH,
    VALIDATOR_ACTIVATION_EPOCH,
    VALIDATOR_EFFECTIVE_BALANCE,
    VALIDATOR_EXIT_EPOCH,
    VALIDATOR_PUBKEY,
    VALIDATOR_SLASHED,
    VALIDATOR_WITHDRAWABLE_EPOCH,
    Validator,
)
from blockchain.beacon_state.state import BeaconStateData, ValidatorFields
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.types import TopUpCandidate


def _build_beacon_state_data(top_up_proof_fixtures) -> BeaconStateData:
    beacon_block_header = top_up_proof_fixtures['beacon_block_header']
    execution_block = top_up_proof_fixtures['execution_block']
    decoded_beacon_state = top_up_proof_fixtures['decoded_beacon_state']
    pubkeys = {bytes.fromhex(w['pubkey'][2:]) for w in top_up_proof_fixtures['validator_witnesses']}

    pubkey_to_index: dict[bytes, int] = {}
    validators_roots: list[bytes] = []
    validators_fields: dict[int, ValidatorFields] = {}
    for index, validator in enumerate(decoded_beacon_state[STATE_VALIDATORS]):
        validators_roots.append(Validator.get_hash_tree_root(validator))
        pubkey = bytes(validator[VALIDATOR_PUBKEY])
        if pubkey in pubkeys:
            pubkey_to_index[pubkey] = index
            validators_fields[index] = ValidatorFields(
                pubkey=pubkey,
                effective_balance=int(validator[VALIDATOR_EFFECTIVE_BALANCE]),
                slashed=bool(validator[VALIDATOR_SLASHED]),
                activation_eligibility_epoch=int(validator[VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH]),
                activation_epoch=int(validator[VALIDATOR_ACTIVATION_EPOCH]),
                exit_epoch=int(validator[VALIDATOR_EXIT_EPOCH]),
                withdrawable_epoch=int(validator[VALIDATOR_WITHDRAWABLE_EPOCH]),
            )

    return BeaconStateData(
        slot=beacon_block_header[0],
        timestamp=int(execution_block['timestamp']),
        parent_beacon_block_root=bytes.fromhex(execution_block['parentBeaconBlockRoot'][2:]),
        state_root=beacon_block_header[3],
        header=beacon_block_header,
        state_field_roots=top_up_proof_fixtures['beacon_state_field_roots'],
        pubkey_to_index=pubkey_to_index,
        pending_deposits={},
        consolidation_targets=set(),
        validators_roots=validators_roots,
        validators_fields=validators_fields,
    )


@pytest.mark.unit
def test_build_topup_proofs_matches_fixture_witnesses(top_up_proof_fixtures):
    beacon_data = _build_beacon_state_data(top_up_proof_fixtures)
    fixture_witnesses = top_up_proof_fixtures['validator_witnesses']
    candidates = [
        TopUpCandidate(
            validator_index=10035,
            key_index=7,
            operator_id=11,
            pubkey=bytes.fromhex(fixture_witnesses[0]['pubkey'][2:]),
            pending_balance=13,
        ),
        TopUpCandidate(
            validator_index=10044,
            key_index=8,
            operator_id=12,
            pubkey=bytes.fromhex(fixture_witnesses[1]['pubkey'][2:]),
            pending_balance=21,
        ),
    ]

    result = build_topup_proofs(beacon_data, candidates)

    assert result.child_block_timestamp == top_up_proof_fixtures['beacon_root_data']['childBlockTimestamp']
    assert result.slot == top_up_proof_fixtures['beacon_root_data']['slot']
    assert result.proposer_index == top_up_proof_fixtures['beacon_root_data']['proposerIndex']
    assert result.validator_indices == [10035, 10044]
    assert result.key_indices == [7, 8]
    assert result.operator_ids == [11, 12]
    assert result.pending_balances_gwei == [13, 21]

    for built_witness, fixture_witness in zip(result.witnesses, fixture_witnesses):
        assert built_witness.proofs == [bytes.fromhex(item[2:]) for item in fixture_witness['proofs']]
        assert built_witness.pubkey == bytes.fromhex(fixture_witness['pubkey'][2:])
        assert built_witness.effective_balance == fixture_witness['effectiveBalance']
        assert built_witness.activation_eligibility_epoch == fixture_witness['activationEligibilityEpoch']
        assert built_witness.activation_epoch == fixture_witness['activationEpoch']
        assert built_witness.exit_epoch == fixture_witness['exitEpoch']
        assert built_witness.withdrawable_epoch == fixture_witness['withdrawableEpoch']
        assert built_witness.slashed == fixture_witness['slashed']


@pytest.mark.unit
def test_build_topup_proofs_rejects_anchor_mismatch(top_up_proof_fixtures):
    beacon_data = _build_beacon_state_data(top_up_proof_fixtures)
    beacon_data.parent_beacon_block_root = b'\x00' * 32
    fixture_witness = top_up_proof_fixtures['validator_witnesses'][0]
    candidates = [
        TopUpCandidate(
            validator_index=10035,
            key_index=7,
            operator_id=11,
            pubkey=bytes.fromhex(fixture_witness['pubkey'][2:]),
            pending_balance=13,
        )
    ]

    with pytest.raises(ValueError, match='beacon_block_root mismatch'):
        build_topup_proofs(beacon_data, candidates)
