from unittest.mock import MagicMock, Mock, patch

import pytest
from web3.types import Wei

from blockchain.beacon_state.ssz_types import FAR_FUTURE_EPOCH
from blockchain.beacon_state.state import BeaconStateData, ValidatorFields
from blockchain.topup.csm02_strategy import CSM02TopUpStrategy
from providers.keys_api import LidoKey

# Small, clear stand-ins for the on-chain TopUpGateway limits (mocked, not the real ~2046 ETH).
TARGET_BALANCE_GWEI = 100
MIN_TOP_UP_GWEI = 10

PK_A = b'\xaa' * 48
PK_B = b'\xbb' * 48

# Large default budget so tests not exercising the allocation cut fund every candidate.
_BIG_ALLOCATION = Wei(10_000 * 10**9)


def _hex(pk: bytes) -> str:
    return '0x' + pk.hex()


def _lido_key(pk: bytes, key_index: int, operator_index: int) -> LidoKey:
    return LidoKey(key=_hex(pk), index=key_index, operatorIndex=operator_index)


def _beacon_data(
    pubkey_to_index: dict[bytes, int],
    balances: dict[bytes, int] | None = None,
    pending: dict[bytes, int] | None = None,
    slashed: set[bytes] | None = None,
    exiting: set[bytes] | None = None,
    not_active: set[bytes] | None = None,
) -> BeaconStateData:
    """A pubkey absent from pubkey_to_index models a key that is still pending on the CL (no index)."""
    balances = balances or {}
    slashed = slashed or set()
    exiting = exiting or set()
    not_active = not_active or set()
    # slot 0 → current_epoch 0, so activation_epoch 1 makes a key "not active yet".
    validators_fields = {
        index: ValidatorFields(
            pubkey=pk,
            effective_balance=balances.get(pk, 0),
            slashed=pk in slashed,
            activation_eligibility_epoch=0,
            activation_epoch=1 if pk in not_active else 0,
            exit_epoch=1 if pk in exiting else FAR_FUTURE_EPOCH,
            withdrawable_epoch=FAR_FUTURE_EPOCH,
        )
        for pk, index in pubkey_to_index.items()
    }
    return BeaconStateData(
        slot=0,
        timestamp=0,
        parent_beacon_block_root=b'',
        state_root=b'',
        header=(0, 0, b'', b'', b''),
        state_field_roots=[],
        pubkey_to_index=pubkey_to_index,
        pending_deposits=pending or {},
        consolidation_targets=set(),
        validators_fields=validators_fields,
    )


def _make_strategy(queue_pubkeys: list[bytes]):
    w3 = MagicMock()
    w3.to_checksum_address.side_effect = lambda address: address
    w3.lido.topup_gateway.get_target_balance_gwei.return_value = TARGET_BALANCE_GWEI
    w3.lido.topup_gateway.get_min_top_up_gwei.return_value = MIN_TOP_UP_GWEI
    csm_contract = Mock()
    csm_contract.get_keys_for_top_up.return_value = queue_pubkeys
    w3.eth.contract.return_value = csm_contract
    strategy = CSM02TopUpStrategy(w3=w3, gas_price_calculator=Mock())
    return strategy, csm_contract


def _call(strategy, keys_api, beacon_data, max_validators=50, module_allocation=_BIG_ALLOCATION):
    with (
        patch('blockchain.topup.csm02_strategy.extract_state_data', return_value=beacon_data),
        patch('blockchain.topup.csm02_strategy.build_topup_proofs') as build_proofs,
    ):
        result = strategy.get_topup_candidates(
            keys_api=keys_api,
            ensure_beacon_state=Mock(),
            module_id=3,
            module_address='0x0000000000000000000000000000000000000003',
            module_allocation=module_allocation,
            max_validators=max_validators,
            consolidation_indexer=Mock(),
        )
    return result, build_proofs


@pytest.mark.unit
def test_builds_candidates_from_queue():
    # Two normal queued keys are topped up; the batch is sorted by validator_index for the proof.
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    beacon_data = _beacon_data({PK_A: 100, PK_B: 50}, balances={PK_A: 40, PK_B: 50}, pending={PK_A: 5})

    result, build_proofs = _call(strategy, keys_api, beacon_data)

    assert result is build_proofs.return_value
    passed_beacon, candidates = build_proofs.call_args.args
    assert passed_beacon is beacon_data
    # sorted by validator_index asc → PK_B (50) before PK_A (100)
    assert [(c.pubkey, c.validator_index, c.key_index, c.operator_id, c.pending_balance) for c in candidates] == [
        (PK_B, 50, 8, 12, 0),
        (PK_A, 100, 7, 11, 5),
    ]


@pytest.mark.unit
def test_empty_queue_returns_none():
    strategy, _ = _make_strategy([])
    keys_api = Mock()
    result, build_proofs = _call(strategy, keys_api, _beacon_data({}))
    assert result is None
    build_proofs.assert_not_called()
    keys_api.get_module_used_keys.assert_not_called()


@pytest.mark.unit
def test_passes_max_validators_to_contract():
    strategy, csm_contract = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]
    _call(strategy, keys_api, _beacon_data({PK_A: 100}, balances={PK_A: 40}), max_validators=37)
    csm_contract.get_keys_for_top_up.assert_called_once_with(37)


@pytest.mark.unit
def test_stops_when_key_pending_on_cl():
    # PK_B is deposited and queued but still pending on the CL (no validator index). We stop the walk
    # at it — it stays in the queue — and keep the keys before it. PK_A is topped up.
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    beacon_data = _beacon_data({PK_A: 10}, balances={PK_A: 40})  # PK_B not on the beacon chain

    _, build_proofs = _call(strategy, keys_api, beacon_data)

    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A]


@pytest.mark.unit
def test_stops_when_key_missing_in_keys_api():
    # PK_B is on the beacon chain but missing from the Keys API. We warn, stop the walk at it, and
    # keep PK_A.
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]  # PK_B missing
    beacon_data = _beacon_data({PK_A: 10, PK_B: 20}, balances={PK_A: 40, PK_B: 40})

    _, build_proofs = _call(strategy, keys_api, beacon_data)

    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A]


@pytest.mark.unit
def test_stops_when_key_not_active():
    # PK_B is queued but not active yet — we can't top it up and must keep it in the queue, so we
    # stop the walk at it. PK_A is topped up.
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    beacon_data = _beacon_data({PK_A: 10, PK_B: 20}, balances={PK_A: 40, PK_B: 40}, not_active={PK_B})

    _, build_proofs = _call(strategy, keys_api, beacon_data)

    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A]


@pytest.mark.unit
def test_returns_none_when_first_queued_key_not_ready():
    # The first queued key is still pending on the CL → nothing collected before the stop → None,
    # so the bot moves on to the next module.
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = []
    result, build_proofs = _call(strategy, keys_api, _beacon_data({}))
    assert result is None
    build_proofs.assert_not_called()


@pytest.mark.unit
def test_stops_at_module_allocation():
    # Both keys need a 60-gwei top-up (target 100 - balance 40). Budget 65 funds PK_A (leaves 5),
    # which is < min(10) → PK_B is cut and the queue tail is not taken.
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    beacon_data = _beacon_data({PK_A: 10, PK_B: 20}, balances={PK_A: 40, PK_B: 40})

    _, build_proofs = _call(strategy, keys_api, beacon_data, module_allocation=Wei(65 * 10**9))

    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A]


@pytest.mark.unit
@pytest.mark.parametrize('kind', ['slashed', 'exiting', 'at_target'])
def test_zero_topup_key_kept_and_flushed(kind):
    # A key the gateway tops up by 0 (slashed / exiting / already at target) stays in the batch to
    # flush it from the queue, but spends nothing from the allocation — so PK_B is still funded
    # within the tight budget.
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    if kind == 'at_target':
        beacon_data = _beacon_data({PK_A: 10, PK_B: 20}, balances={PK_A: 95, PK_B: 40})
    else:
        beacon_data = _beacon_data({PK_A: 10, PK_B: 20}, balances={PK_A: 40, PK_B: 40}, **{kind: {PK_A}})

    # Budget 65: had PK_A spent its 60, only 5 would remain and PK_B would be cut — but PK_A's top-up
    # is 0, so PK_B (60) is still funded.
    _, build_proofs = _call(strategy, keys_api, beacon_data, module_allocation=Wei(65 * 10**9))

    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A, PK_B]


@pytest.mark.unit
def test_all_keys_zero_topup_still_sends_tx():
    # Every queued key is already at target (0 top-up). We still build and send the tx so the gateway
    # flushes these keys out of the queue.
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    beacon_data = _beacon_data({PK_A: 10, PK_B: 20}, balances={PK_A: 95, PK_B: 95})

    result, build_proofs = _call(strategy, keys_api, beacon_data)

    assert result is build_proofs.return_value  # tx built/sent
    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A, PK_B]


@pytest.mark.unit
def test_module_allocation_below_min_returns_none():
    # Budget below the minimum top-up → the first key can't be funded → None.
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]
    result, build_proofs = _call(strategy, keys_api, _beacon_data({PK_A: 10}, balances={PK_A: 40}), module_allocation=Wei(5 * 10**9))
    assert result is None
    build_proofs.assert_not_called()
