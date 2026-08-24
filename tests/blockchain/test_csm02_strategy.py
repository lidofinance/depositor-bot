from unittest.mock import MagicMock, Mock, patch

import pytest
from web3.types import Wei

from blockchain.beacon_state.state import BeaconStateData
from blockchain.topup.csm02_strategy import CSM02TopUpStrategy
from providers.keys_api import LidoKey

PK_A = b'\xaa' * 48
PK_B = b'\xbb' * 48


def _hex(pk: bytes) -> str:
    return '0x' + pk.hex()


def _lido_key(pk: bytes, key_index: int, operator_index: int) -> LidoKey:
    return LidoKey(key=_hex(pk), index=key_index, operatorIndex=operator_index)


def _beacon_data(pubkey_to_index: dict[bytes, int], pending: dict[bytes, int] | None = None) -> BeaconStateData:
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
    )


def _make_strategy(queue_pubkeys: list[bytes]):
    w3 = MagicMock()
    w3.to_checksum_address.side_effect = lambda address: address
    csm_contract = Mock()
    csm_contract.get_keys_for_top_up.return_value = queue_pubkeys
    w3.eth.contract.return_value = csm_contract
    strategy = CSM02TopUpStrategy(w3=w3, gas_price_calculator=Mock())
    return strategy, csm_contract


def _call(strategy, keys_api, beacon_data, max_validators=50):
    with (
        patch('blockchain.topup.csm02_strategy.extract_state_data', return_value=beacon_data),
        patch('blockchain.topup.csm02_strategy.build_topup_proofs') as build_proofs,
    ):
        result = strategy.get_topup_candidates(
            keys_api=keys_api,
            ensure_beacon_state=Mock(),
            module_id=3,
            module_address='0x0000000000000000000000000000000000000003',
            module_allocation=Wei(0),
            max_validators=max_validators,
            consolidation_indexer=Mock(),
        )
    return result, build_proofs


@pytest.mark.unit
def test_builds_candidates_from_queue():
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    beacon_data = _beacon_data({PK_A: 100, PK_B: 50}, pending={PK_A: 5})

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
def test_skips_key_missing_in_keys_api():
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]  # PK_B absent
    result, build_proofs = _call(strategy, keys_api, _beacon_data({PK_A: 100, PK_B: 50}))
    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A]


@pytest.mark.unit
def test_skips_key_missing_in_beacon_state():
    strategy, _ = _make_strategy([PK_A, PK_B])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11), _lido_key(PK_B, 8, 12)]
    result, build_proofs = _call(strategy, keys_api, _beacon_data({PK_A: 100}))  # PK_B not in state
    _, candidates = build_proofs.call_args.args
    assert [c.pubkey for c in candidates] == [PK_A]


@pytest.mark.unit
def test_all_unresolvable_returns_none():
    strategy, _ = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = []
    result, build_proofs = _call(strategy, keys_api, _beacon_data({}))
    assert result is None
    build_proofs.assert_not_called()


@pytest.mark.unit
def test_passes_max_validators_to_contract():
    strategy, csm_contract = _make_strategy([PK_A])
    keys_api = Mock()
    keys_api.get_module_used_keys.return_value = [_lido_key(PK_A, 7, 11)]
    _call(strategy, keys_api, _beacon_data({PK_A: 100}), max_validators=37)
    csm_contract.get_keys_for_top_up.assert_called_once_with(37)
