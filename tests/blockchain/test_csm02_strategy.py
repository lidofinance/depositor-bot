from unittest.mock import MagicMock, Mock, patch

import pytest
from web3.types import Wei

from blockchain.beacon_state.ssz_types import FAR_FUTURE_EPOCH
from blockchain.beacon_state.state import BeaconStateData, ValidatorFields
from blockchain.topup.csm02_strategy import CSM02TopUpStrategy
from providers.keys_api import LidoKey

# Small, clear stand-ins for the on-chain TopUpGateway limits (mocked, not the real ~2046 / ~2 ETH).
TARGET_BALANCE_GWEI = 100
MIN_TOP_UP_GWEI = 10

PK_A = b'\xaa' * 48
PK_B = b'\xbb' * 48

# Default budget comfortably above the minimum so tests not exercising the gate always fund the key.
_BIG_ALLOCATION = Wei(10_000 * 10**9)


def _hex(pk: bytes) -> str:
    return '0x' + pk.hex()


def _lido_key(pk: bytes, key_index: int, operator_index: int) -> LidoKey:
    return LidoKey(key=_hex(pk), index=key_index, operatorIndex=operator_index)


def _beacon_data(
    pubkey_to_index: dict[bytes, int],
    pending: dict[bytes, int] | None = None,
    not_active: set[bytes] | None = None,
    slashed: set[bytes] | None = None,
    exiting: set[bytes] | None = None,
    balances: dict[bytes, int] | None = None,
) -> BeaconStateData:
    """The strategy reads pubkey_to_index, the head's fields (activation/slashed/exit/balance) and
    pending_deposits; the rest is used by the (mocked) build_topup_proofs. A pubkey absent from
    pubkey_to_index models a key still pending on the CL. slot 0 → current_epoch 0, so activation_epoch
    1 makes a key not active. effective_balance defaults to 0, i.e. a fundable head."""
    not_active = not_active or set()
    slashed = slashed or set()
    exiting = exiting or set()
    balances = balances or {}
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


def _call(strategy, keys_api, beacon_data, max_validators=50, module_allocation=_BIG_ALLOCATION, ensure=None):
    ensure = ensure or Mock(return_value=beacon_data)
    with (
        patch('blockchain.topup.csm02_strategy.extract_state_data', return_value=beacon_data),
        patch('blockchain.topup.csm02_strategy.build_topup_proofs') as build_proofs,
    ):
        result = strategy.get_topup_candidates(
            keys_api=keys_api,
            ensure_beacon_state=ensure,
            module_id=3,
            module_address='0x0000000000000000000000000000000000000003',
            module_allocation=module_allocation,
            max_validators=max_validators,
            consolidation_indexer=Mock(),
        )
    return result, build_proofs


@pytest.mark.unit
def test_builds_single_candidate_from_queue_head():
    # One key from the queue head is resolved and turned into a single-candidate proof.
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]
    beacon_data = _beacon_data({PK_A: 100}, pending={PK_A: 5})

    result, build_proofs = _call(strategy, keys_api, beacon_data)

    assert result is build_proofs.return_value
    passed_beacon, candidates = build_proofs.call_args.args
    assert passed_beacon is beacon_data
    assert [(c.pubkey, c.validator_index, c.key_index, c.operator_id, c.pending_balance) for c in candidates] == [
        (PK_A, 100, 7, 11, 5),
    ]


@pytest.mark.unit
def test_requests_a_single_key_from_the_queue():
    # Regardless of max_validators, CSM pulls exactly one key (the queue head).
    strategy, csm_contract = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]
    _call(strategy, keys_api, _beacon_data({PK_A: 100}), max_validators=37)
    csm_contract.get_keys_for_top_up.assert_called_once_with(1)


@pytest.mark.unit
def test_empty_queue_returns_none():
    strategy, _ = _make_strategy([])
    keys_api = Mock()
    result, build_proofs = _call(strategy, keys_api, _beacon_data({}))
    assert result is None
    build_proofs.assert_not_called()
    keys_api.get_module_used_keys.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize('allocation', [Wei(0), Wei(5 * 10**9)])  # zero and below-min: same skip branch
def test_fundable_head_without_enough_allocation_skips(allocation):
    # A fundable head (positive gateway limit) with allocation below a minimal top-up (0 included) →
    # nothing to fund and nothing to flush → skip, so the bot moves on to the next module.
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]
    result, build_proofs = _call(strategy, keys_api, _beacon_data({PK_A: 5}), module_allocation=allocation)
    assert result is None
    build_proofs.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    'beacon_kwargs',
    [
        {'slashed': {PK_A}},
        {'exiting': {PK_A}},
        {'balances': {PK_A: TARGET_BALANCE_GWEI}},  # at target: headroom 0
        {'balances': {PK_A: TARGET_BALANCE_GWEI - 1}},  # headroom 1 < min 10
    ],
)
def test_flushes_zero_limit_head_at_zero_allocation(beacon_kwargs):
    # A zero-limit head (slashed / exiting / at target / headroom < min) is submitted even at zero
    # allocation so the module dequeues it (flush).
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]
    beacon_data = _beacon_data({PK_A: 5}, **beacon_kwargs)

    result, build_proofs = _call(strategy, keys_api, beacon_data, module_allocation=Wei(0))

    assert result is build_proofs.return_value
    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A]


@pytest.mark.unit
def test_returns_none_when_key_pending_on_cl():
    # The queued key has no validator index yet (still a pending deposit) → can't prove it → None.
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    result, build_proofs = _call(strategy, keys_api, _beacon_data({}))  # PK_A not on the beacon chain
    assert result is None
    build_proofs.assert_not_called()


@pytest.mark.unit
def test_returns_none_when_key_missing_in_keys_api():
    # The key is on the beacon chain but absent from the Keys API → warn and skip.
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = []  # PK_A missing
    result, build_proofs = _call(strategy, keys_api, _beacon_data({PK_A: 100}))
    assert result is None
    build_proofs.assert_not_called()


@pytest.mark.unit
def test_returns_none_when_head_not_active():
    # The head is on the beacon chain but not active yet → don't top it up, move to the next module.
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    result, build_proofs = _call(strategy, keys_api, _beacon_data({PK_A: 100}, not_active={PK_A}))
    assert result is None
    build_proofs.assert_not_called()


@pytest.mark.unit
def test_picks_matching_key_from_module_used_keys():
    # get_keys_for_top_up returns one pubkey; the Keys API response may hold many — pick the match.
    strategy, _ = _make_strategy([PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    beacon_data = _beacon_data({PK_A: 100, PK_B: 50})

    _, build_proofs = _call(strategy, keys_api, beacon_data)

    _, candidates = build_proofs.call_args.args
    assert [(c.pubkey, c.validator_index, c.key_index, c.operator_id) for c in candidates] == [(PK_B, 50, 8, 12)]
