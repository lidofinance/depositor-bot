from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from blockchain.beacon_state.ssz_types import (
    FAR_FUTURE_EPOCH,
    STATE_BALANCES,
    STATE_VALIDATORS,
    VALIDATOR_ACTIVATION_EPOCH,
    VALIDATOR_EFFECTIVE_BALANCE,
    VALIDATOR_EXIT_EPOCH,
    VALIDATOR_SLASHED,
)
from blockchain.beacon_state.state import BeaconStateData
from blockchain.topup.cmv2_strategy import (
    MAX_TOP_UP_BALANCE_GWEI,
    CMv2TopUpStrategy,
    _check_key_eligibility,
    _collect_pubkeys,
    _select_operator_candidates,
    _take_up_to_allocation,
)
from blockchain.topup.types import TopUpCandidate
from providers.keys_api import LidoKey
from web3.types import Wei


def _build_beacon_state_data(top_up_proof_fixtures) -> BeaconStateData:
    beacon_block_header = top_up_proof_fixtures['beacon_block_header']
    execution_block = top_up_proof_fixtures['execution_block']
    decoded_beacon_state = top_up_proof_fixtures['decoded_beacon_state']
    state: list[Any] = list(decoded_beacon_state)
    state[STATE_VALIDATORS] = list(decoded_beacon_state[STATE_VALIDATORS])
    state[STATE_BALANCES] = list(decoded_beacon_state[STATE_BALANCES])
    pubkeys = {bytes.fromhex(w['pubkey'][2:]) for w in top_up_proof_fixtures['validator_witnesses']}

    pubkey_to_index = {}
    for index, validator in enumerate(state[STATE_VALIDATORS]):
        pubkey = bytes(validator[0])
        if pubkey in pubkeys:
            pubkey_to_index[pubkey] = index

    return BeaconStateData(
        slot=beacon_block_header[0],
        timestamp=int(execution_block['timestamp']),
        parent_beacon_block_root=bytes.fromhex(execution_block['parentBeaconBlockRoot'][2:]),
        state_root=beacon_block_header[3],
        header=beacon_block_header,
        state=state,
        state_field_roots=top_up_proof_fixtures['beacon_state_field_roots'],
        pubkey_to_index=pubkey_to_index,
        pending_deposits={},
        consolidation_targets=set(),
    )


def _make_validator(
    pubkey=b'\x00' * 48,
    withdrawal_credentials=b'\x00' * 32,
    effective_balance=0,
    slashed=False,
    activation_eligibility_epoch=0,
    activation_epoch=0,
    exit_epoch=FAR_FUTURE_EPOCH,
    withdrawable_epoch=FAR_FUTURE_EPOCH,
):
    return [
        pubkey,
        withdrawal_credentials,
        effective_balance,
        slashed,
        activation_eligibility_epoch,
        activation_epoch,
        exit_epoch,
        withdrawable_epoch,
    ]


def _make_key(pubkey: str, key_index: int, operator_index: int) -> LidoKey:
    return LidoKey(
        index=key_index,
        operatorIndex=operator_index,
        depositSignature='0x',
        key=pubkey,
        used=True,
        moduleAddress='0x0000000000000000000000000000000000000001',
        vetted=True,
    )


@pytest.mark.unit
def test_get_cmv2_topup_candidates_builds_proofs_from_fixture_data(top_up_proof_fixtures):
    beacon_data = _build_beacon_state_data(top_up_proof_fixtures)
    witnesses = top_up_proof_fixtures['validator_witnesses']
    key_1 = _make_key(witnesses[0]['pubkey'], 7, 11)
    key_2 = _make_key(witnesses[1]['pubkey'], 8, 12)

    w3 = MagicMock()
    w3.to_checksum_address.side_effect = lambda address: address
    cmv2_contract = Mock()
    cmv2_contract.get_deposits_allocation.return_value = (
        32 * 10**18,
        [11, 12],
        [16 * 10**18, 16 * 10**18],
    )
    w3.eth.contract.return_value = cmv2_contract

    keys_api = Mock()
    keys_api.get_module_operator_used_keys.return_value = {11: [key_1], 12: [key_2]}
    cl = Mock()

    strategy = CMv2TopUpStrategy(w3=w3, gas_price_calculator=Mock())

    with patch('blockchain.topup.cmv2_strategy.load_beacon_state_data', return_value=beacon_data) as load_beacon_state_data:
        result = strategy.get_topup_candidates(
            keys_api=keys_api,
            cl=cl,
            module_id=1,
            module_address='0x0000000000000000000000000000000000000002',
            module_allocation=Wei(32 * 10**18),
            max_validators=50,
        )

    assert result is not None
    assert result.key_indices == [7, 8]
    assert result.operator_ids == [11, 12]
    assert result.validator_indices == [int(witnesses[0]['validatorIndex']), int(witnesses[1]['validatorIndex'])]
    assert [w.pubkey for w in result.witnesses] == [bytes.fromhex(witnesses[0]['pubkey'][2:]), bytes.fromhex(witnesses[1]['pubkey'][2:])]

    keys_api.get_module_operator_used_keys.assert_called_once_with(1, [11, 12])
    load_beacon_state_data.assert_called_once()


@pytest.mark.unit
def test_collect_pubkeys():
    key_1 = _make_key('0x' + '11' * 48, 1, 10)
    key_2 = _make_key('0x' + '22' * 48, 2, 11)
    key_3 = _make_key('0x' + '11' * 48, 3, 12)

    result = _collect_pubkeys({10: [key_1], 11: [key_2], 12: [key_3]})

    assert result == {bytes.fromhex('11' * 48), bytes.fromhex('22' * 48)}


@pytest.mark.unit
def test_check_key_eligibility_returns_candidate(top_up_proof_fixtures):
    beacon_data = _build_beacon_state_data(top_up_proof_fixtures)
    witness = top_up_proof_fixtures['validator_witnesses'][0]
    key = _make_key(witness['pubkey'], 7, 11)

    candidate = _check_key_eligibility(key, beacon_data)

    assert candidate == TopUpCandidate(
        validator_index=int(witness['validatorIndex']),
        key_index=7,
        operator_id=11,
        pubkey=bytes.fromhex(witness['pubkey'][2:]),
        pending_balance=0,
    )


@pytest.mark.unit
def test_check_key_eligibility_rejects_invalid_cases(top_up_proof_fixtures):
    beacon_data = _build_beacon_state_data(top_up_proof_fixtures)
    witness = top_up_proof_fixtures['validator_witnesses'][0]
    pubkey = bytes.fromhex(witness['pubkey'][2:])
    validator_index = int(witness['validatorIndex'])
    key = _make_key(witness['pubkey'], 7, 11)

    assert _check_key_eligibility(_make_key('0x' + '33' * 48, 7, 11), beacon_data) is None

    beacon_data.consolidation_targets = {validator_index}
    assert _check_key_eligibility(key, beacon_data) is None
    beacon_data.consolidation_targets = set()

    validator = list(beacon_data.state[STATE_VALIDATORS][validator_index])
    validator[VALIDATOR_SLASHED] = True
    beacon_data.state[STATE_VALIDATORS][validator_index] = tuple(validator)
    assert _check_key_eligibility(key, beacon_data) is None

    validator[VALIDATOR_SLASHED] = False
    validator[VALIDATOR_EXIT_EPOCH] = 1
    beacon_data.state[STATE_VALIDATORS][validator_index] = tuple(validator)
    assert _check_key_eligibility(key, beacon_data) is None

    validator[VALIDATOR_EXIT_EPOCH] = FAR_FUTURE_EPOCH
    validator[VALIDATOR_ACTIVATION_EPOCH] = beacon_data.slot + 1
    beacon_data.state[STATE_VALIDATORS][validator_index] = tuple(validator)
    assert _check_key_eligibility(key, beacon_data) is None

    validator[VALIDATOR_ACTIVATION_EPOCH] = 0
    validator[VALIDATOR_EFFECTIVE_BALANCE] = MAX_TOP_UP_BALANCE_GWEI
    beacon_data.state[STATE_VALIDATORS][validator_index] = tuple(validator)
    beacon_data.pending_deposits = {pubkey: 1}
    assert _check_key_eligibility(key, beacon_data) is None


@pytest.mark.unit
def test_select_operator_candidates_sorts_by_key_index():
    beacon_data = Mock()
    keys = [
        _make_key('0x' + '22' * 48, 8, 11),
        _make_key('0x' + '11' * 48, 7, 11),
    ]

    with (
        patch(
            'blockchain.topup.cmv2_strategy._check_key_eligibility',
            side_effect=[
                TopUpCandidate(1, 8, 11, bytes.fromhex('22' * 48), 0),
                TopUpCandidate(0, 7, 11, bytes.fromhex('11' * 48), 0),
            ],
        ),
        patch('blockchain.topup.cmv2_strategy._take_up_to_allocation', side_effect=lambda candidates, allocation, _: candidates) as take,
    ):
        result = _select_operator_candidates(keys, 16 * 10**18, beacon_data)

    assert [candidate.key_index for candidate in result] == [7, 8]
    assert take.call_args.args[0] == result


@pytest.mark.unit
def test_take_up_to_allocation_respects_remaining_and_skips_zero_topup():
    state: list[Any] = [None] * (STATE_VALIDATORS + 1)
    state[STATE_VALIDATORS] = [
        _make_validator(effective_balance=MAX_TOP_UP_BALANCE_GWEI - 10),  # needs 10 Gwei
        _make_validator(effective_balance=MAX_TOP_UP_BALANCE_GWEI - 20),  # needs 20 Gwei
        _make_validator(effective_balance=MAX_TOP_UP_BALANCE_GWEI),  # needs 0 Gwei — skip
    ]
    beacon_data = Mock(state=state)
    candidates = [
        TopUpCandidate(0, 1, 11, b'a', 0),
        TopUpCandidate(1, 2, 11, b'b', 0),
        TopUpCandidate(2, 3, 11, b'c', 0),
    ]

    # 15 Gwei in Wei — enough for candidate 0 (10 Gwei), then 10+20=30 > 15 so stops after candidate 1
    result = _take_up_to_allocation(candidates, 15 * 10**9, beacon_data)

    assert result == candidates[:2]


@pytest.mark.unit
def test_take_up_to_allocation_log_scenario_1216_eth():
    """Reproduces devnet log: allocation=1216 ETH, 25 validators each with 32 ETH balance.
    topup per validator = 2045.75 - 32 = 2013.75 ETH > 1216 ETH allocation,
    so only 1 candidate should be selected.
    """
    balance_gwei = 32 * 10**9  # 32 ETH in Gwei
    state: list[Any] = [None] * (STATE_VALIDATORS + 1)
    state[STATE_VALIDATORS] = [_make_validator(effective_balance=balance_gwei) for _ in range(25)]
    beacon_data = Mock(state=state)

    candidates = [TopUpCandidate(i, i, 0, bytes([i]), 0) for i in range(25)]

    # 1216 ETH in Wei — from the log
    allocation_wei = 1216 * 10**18
    result = _take_up_to_allocation(candidates, allocation_wei, beacon_data)

    # topup per validator = 2_013_750_000_000 Gwei (2013.75 ETH) > 1216 ETH allocation
    # first candidate exhausts allocation → only 1 selected
    assert len(result) == 1
