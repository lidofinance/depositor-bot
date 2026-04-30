from unittest.mock import Mock

import pytest


@pytest.mark.unit
def test_csm_deposit_strategy(csm_strategy):
    csm_strategy.deposited_keys_amount = Mock(return_value=1)
    assert not csm_strategy.can_deposit_keys_based_on_ether(3)

    csm_strategy.deposited_keys_amount = Mock(return_value=2)
    csm_strategy._gas_price_calculator.get_pending_base_fee = Mock(return_value=10)
    assert csm_strategy.can_deposit_keys_based_on_ether(3)


# ─── can_deposit_keys_based_on_allocation ──────────────────────────


def _digest(module_id):
    """Minimal digest where digest[2][0] is the module_id."""
    return (0, 0, (module_id, '', 0, 0, 0, 0, '', 0, 0, 0, 0, 0, 0, 1, 0, 0), (0, 0, 0))


def _setup_allocation(strategy, module_id, allocated_wei, depositable=100 * 10**18):
    strategy.w3.lido.lido.get_depositable_ether = Mock(return_value=depositable)
    strategy.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [allocated_wei], [0]))
    strategy.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[_digest(module_id)])


@pytest.mark.unit
def test_allocation_no_depositable_ether_returns_false(base_deposit_strategy):
    base_deposit_strategy.w3.lido.lido.get_depositable_ether = Mock(return_value=0)
    base_deposit_strategy.w3.lido.staking_router.get_deposit_allocations = Mock()

    assert base_deposit_strategy.can_deposit_keys_based_on_allocation(1) is False
    base_deposit_strategy.w3.lido.staking_router.get_deposit_allocations.assert_not_called()


@pytest.mark.unit
def test_allocation_module_not_in_digests_returns_false(base_deposit_strategy):
    base_deposit_strategy.w3.lido.lido.get_depositable_ether = Mock(return_value=100 * 10**18)
    base_deposit_strategy.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [32 * 10**18], [0]))
    base_deposit_strategy.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[_digest(2)])

    assert base_deposit_strategy.can_deposit_keys_based_on_allocation(99) is False


@pytest.mark.unit
def test_allocation_below_32eth_rounds_to_zero(base_deposit_strategy):
    # 16 ETH // 32 ETH == 0 keys → below threshold=1
    _setup_allocation(base_deposit_strategy, module_id=1, allocated_wei=16 * 10**18)

    assert base_deposit_strategy.can_deposit_keys_based_on_allocation(1) is False


@pytest.mark.unit
def test_allocation_one_key_gas_ok_returns_true(base_deposit_strategy):
    # 32 ETH → 1 key. _recommended_max_gas(1) = (1 + 100) * 1e8 = 1.01e10. base_fee=1 → ok
    _setup_allocation(base_deposit_strategy, module_id=1, allocated_wei=32 * 10**18)
    base_deposit_strategy._gas_price_calculator.get_pending_base_fee = Mock(return_value=1)

    assert base_deposit_strategy.can_deposit_keys_based_on_allocation(1) is True


@pytest.mark.unit
def test_allocation_two_keys_gas_too_high_returns_false(base_deposit_strategy):
    # 64 ETH → 2 keys. _recommended_max_gas(2) = (8 + 100) * 1e8 = 1.08e10. base_fee=1e12 → fail
    _setup_allocation(base_deposit_strategy, module_id=1, allocated_wei=64 * 10**18)
    base_deposit_strategy._gas_price_calculator.get_pending_base_fee = Mock(return_value=10**12)

    assert base_deposit_strategy.can_deposit_keys_based_on_allocation(1) is False


@pytest.mark.unit
def test_allocation_calls_get_deposit_allocations_with_top_up_true(base_deposit_strategy):
    _setup_allocation(base_deposit_strategy, module_id=1, allocated_wei=32 * 10**18)
    base_deposit_strategy._gas_price_calculator.get_pending_base_fee = Mock(return_value=1)

    base_deposit_strategy.can_deposit_keys_based_on_allocation(1)

    base_deposit_strategy.w3.lido.staking_router.get_deposit_allocations.assert_called_once_with(100 * 10**18, is_top_up=True)


@pytest.mark.unit
def test_allocation_lookup_by_module_id_not_index(base_deposit_strategy):
    """Allocation must be picked by digest[2][0] == module_id, not by list position."""
    base_deposit_strategy.w3.lido.lido.get_depositable_ether = Mock(return_value=300 * 10**18)
    # digests=[m1, m2, m3]; allocations=[100, 200, 64] ETH → module_id=3 must get 64 ETH (2 keys)
    base_deposit_strategy.w3.lido.staking_router.get_deposit_allocations = Mock(
        return_value=(0, [100 * 10**18, 200 * 10**18, 64 * 10**18], [0, 0, 0])
    )
    base_deposit_strategy.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[_digest(1), _digest(2), _digest(3)])

    assert base_deposit_strategy._allocated_keys_amount(3) == 2


@pytest.mark.unit
def test_csm_allocation_one_key_below_threshold_returns_false(csm_strategy):
    # CSM threshold = 2, so 1 key fails
    _setup_allocation(csm_strategy, module_id=3, allocated_wei=32 * 10**18)

    assert csm_strategy.can_deposit_keys_based_on_allocation(3) is False


@pytest.mark.unit
def test_csm_allocation_two_keys_above_threshold_returns_true(csm_strategy):
    # CSM gas check is always True; 2 keys >= threshold=2
    _setup_allocation(csm_strategy, module_id=3, allocated_wei=64 * 10**18)
    csm_strategy._gas_price_calculator.get_pending_base_fee = Mock(return_value=1)

    assert csm_strategy.can_deposit_keys_based_on_allocation(3) is True
