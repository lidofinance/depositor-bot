import unittest
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import MagicMock, Mock

import pytest
import variables
from bots.depositor import DepositorBot

from tests.conftest import COUNCIL_ADDRESS_1, COUNCIL_ADDRESS_2, COUNCIL_PK_1, COUNCIL_PK_2
from tests.utils.protocol_utils import get_deposit_message

# ─── Shared helpers ────────────────────────────────────────────────


def _make_digest(module_id, address, wc_type):
    """digest[2] = StakingModule tuple: (id, address, ..., wc_type@13, ...)."""
    return (
        10,
        5,
        (module_id, address, 500, 500, 1000, 0, f'module{module_id}', 0, 0, 0, 0, 150, 25, wc_type, 0, 0),
        (0, 100, 10),
    )


def _make_bot():
    """Build a DepositorBot with all-MagicMock deps. No transports → MessageStorage stays empty."""
    variables.MESSAGE_TRANSPORTS = ''
    return DepositorBot(
        w3=MagicMock(),
        sender=MagicMock(),
        base_deposit_strategy=MagicMock(),
        csm_strategy=MagicMock(),
        gas_price_calculator=MagicMock(),
        keys_api=MagicMock(),
        cl=MagicMock(),
    )


# ─── _refresh_modules_state ────────────────────────────────────────


@pytest.mark.unit
class TestRefreshModulesState(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        self.bot._module_last_heart_beat = {1: datetime.now(), 2: datetime.now(), 3: datetime.now()}

    def test_calls_quorum_for_each_whitelisted(self):
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._select_strategy = Mock(return_value=Mock())

        self.bot._refresh_modules_state()

        called_ids = sorted(c.args[0] for c in self.bot._get_quorum.call_args_list)
        self.assertEqual([1, 2, 3], called_ids)

    def test_calls_gas_probe_for_each_whitelisted(self):
        self.bot._get_quorum = Mock(return_value=None)
        strategy = Mock()
        self.bot._select_strategy = Mock(return_value=strategy)

        self.bot._refresh_modules_state()

        # is_gas_price_ok called once per whitelisted module
        self.assertEqual(3, strategy.is_gas_price_ok.call_count)

    def test_heartbeat_refreshed_on_truthy_quorum(self):
        self.bot._get_quorum = Mock(return_value=['msg'])  # truthy
        self.bot._select_strategy = Mock(return_value=Mock())

        old = datetime.now() - timedelta(hours=2)
        self.bot._module_last_heart_beat = {1: old, 2: old, 3: old}

        self.bot._refresh_modules_state()

        for module_id in [1, 2, 3]:
            self.assertGreater(self.bot._module_last_heart_beat[module_id], old)

    def test_heartbeat_not_refreshed_on_none_quorum(self):
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._select_strategy = Mock(return_value=Mock())

        old = datetime.now() - timedelta(hours=2)
        self.bot._module_last_heart_beat = {1: old, 2: old, 3: old}

        self.bot._refresh_modules_state()

        for module_id in [1, 2, 3]:
            self.assertEqual(old, self.bot._module_last_heart_beat[module_id])

    def test_empty_whitelist_noop(self):
        variables.DEPOSIT_MODULES_WHITELIST = []
        self.bot._get_quorum = Mock()
        self.bot._select_strategy = Mock()

        self.bot._refresh_modules_state()

        self.bot._get_quorum.assert_not_called()
        self.bot._select_strategy.assert_not_called()

    def test_quorum_called_only_for_whitelisted(self):
        # Regression: previous implementation accidentally iterated all SR modules.
        variables.DEPOSIT_MODULES_WHITELIST = [1, 3]
        self.bot._module_last_heart_beat = {1: datetime.now(), 3: datetime.now()}
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._select_strategy = Mock(return_value=Mock())

        self.bot._refresh_modules_state()

        called_ids = sorted(c.args[0] for c in self.bot._get_quorum.call_args_list)
        self.assertEqual([1, 3], called_ids)



# ─── _is_in_cooldown ───────────────────────────────────────────────


@pytest.mark.unit
class TestIsInCooldown(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1]

    def test_fresh_returns_true(self):
        self.bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=1)
        self.assertTrue(self.bot._is_in_cooldown(1))

    def test_stale_returns_false(self):
        self.bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)
        self.assertFalse(self.bot._is_in_cooldown(1))

    def test_at_boundary_returns_true(self):
        # The contract is `<=` — exactly at the boundary still counts as cooldown.
        self.bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES, seconds=-1)
        self.assertTrue(self.bot._is_in_cooldown(1))


# ─── _phase_seed ───────────────────────────────────────────────────


@pytest.mark.unit
class TestPhaseSeed(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        # Fresh heartbeats → all modules are in cooldown by default.
        self.bot._module_last_heart_beat = {m: datetime.now() for m in [1, 2, 3]}
        self.bot.w3.lido.deposit_security_module.can_deposit.return_value = True
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._deposit_to_module = Mock(return_value=True)

    def _set_cooldown_expired(self, module_id):
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    # ─── Filters ───────────────────────────────────────────────

    def test_filters_non_0x02(self):
        digests = [_make_digest(1, '0xA1', 1)]
        done, success = self.bot._phase_seed([50], [100], digests)
        self.assertEqual((False, False), (done, success))
        self.bot._deposit_to_module.assert_not_called()

    def test_filters_zero_allocation(self):
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2)]
        self.bot._get_quorum = Mock(return_value=['msg'])
        # module 1: allocated=0 → skipped; module 2: allocated=50 → deposits
        self.bot._phase_seed([0, 50], [0, 100], digests)
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_filters_non_whitelisted(self):
        digests = [_make_digest(4, '0xA4', 2)]
        done, success = self.bot._phase_seed([50], [100], digests)
        self.assertEqual((False, False), (done, success))
        self.bot._deposit_to_module.assert_not_called()

    # ─── Sort & selection ──────────────────────────────────────

    def test_sorts_by_stake_asc(self):
        # stake = new - allocated. Lowest stake first.
        # m1: 110-10=100; m2: 70-50=20 (lowest); m3: 80-30=50
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2), _make_digest(3, '0xA3', 2)]
        self.bot._get_quorum = Mock(return_value=['msg'])

        done, success = self.bot._phase_seed([10, 50, 30], [110, 70, 80], digests)

        self.assertEqual((True, True), (done, success))
        # Lowest-stake module (id=2) is tried first.
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_index_alignment_with_subset_whitelist(self):
        # SR returns 4 modules; WHITELIST = [1, 3]. Allocations are indexed by SR list.
        variables.DEPOSIT_MODULES_WHITELIST = [1, 3]
        self.bot._module_last_heart_beat = {1: datetime.now(), 3: datetime.now()}
        digests = [
            _make_digest(1, '0xA1', 2),
            _make_digest(2, '0xA2', 2),  # not whitelisted
            _make_digest(3, '0xA3', 2),
            _make_digest(4, '0xA4', 2),  # not whitelisted
        ]
        self.bot._get_quorum = Mock(return_value=['msg'])
        # m1 stake = 70-50 = 20 (lowest); m3 stake = 80-30 = 50
        self.bot._phase_seed([50, 999, 30, 999], [70, 999, 80, 999], digests)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_empty_digests_returns_done_false(self):
        done, success = self.bot._phase_seed([], [], [])
        self.assertEqual((False, False), (done, success))

    # ─── Iteration ─────────────────────────────────────────────

    def test_can_deposit_false_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2)]
        # m2 has lower stake → tried first; can_deposit=False on m2 → fall to m1
        self.bot.w3.lido.deposit_security_module.can_deposit.side_effect = lambda mid: mid != 2
        self.bot._get_quorum = Mock(return_value=['msg'])

        self.bot._phase_seed([10, 50], [110, 70], digests)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_single_with_quorum_deposits(self):
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._get_quorum = Mock(return_value=['msg'])

        done, success = self.bot._phase_seed([50], [100], digests)

        self.assertEqual((True, True), (done, success))
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_cooldown_active_no_quorum_stops_phase(self):
        # Cooldown active (fresh heartbeat) + no quorum → stop phase, don't proceed.
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._get_quorum = Mock(return_value=None)

        done, success = self.bot._phase_seed([50], [100], digests)

        self.assertEqual((True, False), (done, success))
        self.bot._deposit_to_module.assert_not_called()

    def test_cooldown_expired_no_quorum_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2)]
        # m2 lower stake (tried first), cooldown expired → next; m1 has quorum
        self._set_cooldown_expired(2)
        self.bot._get_quorum = Mock(side_effect=lambda mid: ['msg'] if mid == 1 else None)

        self.bot._phase_seed([10, 50], [110, 70], digests)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_all_cooldowns_expired_returns_done_false(self):
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2)]
        self._set_cooldown_expired(1)
        self._set_cooldown_expired(2)
        self.bot._get_quorum = Mock(return_value=None)

        done, success = self.bot._phase_seed([30, 50], [50, 100], digests)

        self.assertEqual((False, False), (done, success))
        self.bot._deposit_to_module.assert_not_called()

    def test_deposit_failure_still_returns_done_true(self):
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._get_quorum = Mock(return_value=['msg'])
        self.bot._deposit_to_module = Mock(return_value=False)

        done, success = self.bot._phase_seed([50], [100], digests)

        # done=True → caller stops; success=False → no deposit
        self.assertEqual((True, False), (done, success))


# ─── _phase_full ───────────────────────────────────────────────────


@pytest.mark.unit
class TestPhaseFull(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        self.bot._module_last_heart_beat = {m: datetime.now() for m in [1, 2, 3]}
        self.bot.w3.lido.deposit_security_module.can_deposit.return_value = True
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._deposit_to_module = Mock(return_value=True)

    def _set_cooldown_expired(self, module_id):
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    def test_filters_non_0x01(self):
        digests = [_make_digest(1, '0xA1', 2)]
        done, success = self.bot._phase_full([50], [100], digests)
        self.assertEqual((False, False), (done, success))
        self.bot._deposit_to_module.assert_not_called()

    def test_filters_zero_seed_allocation(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        self.bot._get_quorum = Mock(return_value=['msg'])
        self.bot._phase_full([0, 50], [0, 100], digests)
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_filters_non_whitelisted(self):
        digests = [_make_digest(4, '0xA4', 1)]
        done, success = self.bot._phase_full([50], [100], digests)
        self.assertEqual((False, False), (done, success))
        self.bot._deposit_to_module.assert_not_called()

    def test_sorts_by_stake_asc(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1), _make_digest(3, '0xA3', 1)]
        self.bot._get_quorum = Mock(return_value=['msg'])
        # m2 stake = 70-50 = 20 (lowest)
        self.bot._phase_full([10, 50, 30], [110, 70, 80], digests)
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_can_deposit_false_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        self.bot.w3.lido.deposit_security_module.can_deposit.side_effect = lambda mid: mid != 2
        self.bot._get_quorum = Mock(return_value=['msg'])
        self.bot._phase_full([10, 50], [110, 70], digests)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_quorum_active_deposits(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self.bot._get_quorum = Mock(return_value=['msg'])

        done, success = self.bot._phase_full([50], [100], digests)

        self.assertEqual((True, True), (done, success))
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_cooldown_active_stops_phase(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self.bot._get_quorum = Mock(return_value=None)

        done, success = self.bot._phase_full([50], [100], digests)

        self.assertEqual((True, False), (done, success))
        self.bot._deposit_to_module.assert_not_called()

    def test_cooldown_expired_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        self._set_cooldown_expired(2)
        self.bot._get_quorum = Mock(side_effect=lambda mid: ['msg'] if mid == 1 else None)

        self.bot._phase_full([10, 50], [110, 70], digests)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_empty_digests_returns_done_false(self):
        done, success = self.bot._phase_full([], [], [])
        self.assertEqual((False, False), (done, success))


# ─── _phase_full_and_topup ─────────────────────────────────────────


@pytest.mark.unit
class TestPhaseFullAndTopup(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        self.bot._module_last_heart_beat = {m: datetime.now() for m in [1, 2, 3]}
        self.bot.w3.lido.deposit_security_module.can_deposit.return_value = True
        self.bot.w3.lido.topup_gateway.can_top_up.return_value = True
        self.bot.w3.lido.topup_gateway.is_block_distance_passed.return_value = True
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=True)

    def _set_cooldown_expired(self, module_id):
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    def _set_topup_allocation(self, allocated, new):
        """Stub get_deposit_allocations(is_top_up=True) → (total, allocated, new)."""
        self.bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(sum(allocated), allocated, new))

    # ─── Filters ───────────────────────────────────────────────

    def test_filters_non_whitelisted(self):
        variables.DEPOSIT_MODULES_WHITELIST = [1]
        digests = [_make_digest(2, '0xA2', 2), _make_digest(3, '0xA3', 1)]
        self._set_topup_allocation([50, 50], [100, 100])
        done, success = self.bot._phase_full_and_topup(100, [0, 50], [0, 100], digests)
        self.assertEqual((False, False), (done, success))
        self.bot._top_up_to_module.assert_not_called()
        self.bot._deposit_to_module.assert_not_called()

    def test_filters_zero_allocation_per_type(self):
        # 0x02 → check topup_allocated; 0x01 → check seed_allocated
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 1)]
        # 0x02 m1: topup=0 → skipped; 0x01 m2: seed=0 → skipped
        self._set_topup_allocation([0, 50], [0, 100])
        self.bot._get_quorum = Mock(return_value=['msg'])

        done, success = self.bot._phase_full_and_topup(100, [50, 0], [100, 0], digests)

        self.assertEqual((False, False), (done, success))
        self.bot._top_up_to_module.assert_not_called()
        self.bot._deposit_to_module.assert_not_called()

    def test_index_alignment_with_subset_whitelist(self):
        variables.DEPOSIT_MODULES_WHITELIST = [1, 3]
        self.bot._module_last_heart_beat = {1: datetime.now(), 3: datetime.now()}
        digests = [
            _make_digest(1, '0xA1', 2),
            _make_digest(2, '0xA2', 2),  # not whitelisted
            _make_digest(3, '0xA3', 1),
            _make_digest(4, '0xA4', 1),  # not whitelisted
        ]
        # m1: topup_alloc=50, stake=70-50=20 (lowest); m3: seed_alloc=30, stake=80-30=50
        self._set_topup_allocation([50, 999, 999, 999], [70, 999, 999, 999])
        self.bot._get_quorum = Mock(return_value=['msg'])

        self.bot._phase_full_and_topup(100, [999, 999, 30, 999], [999, 999, 80, 999], digests)

        # m1 (0x02) goes first
        self.bot._top_up_to_module.assert_called_once_with(1, '0xA1', 50)
        self.bot._deposit_to_module.assert_not_called()

    def test_sorts_by_per_type_stake_asc(self):
        # 0x02 stake from topup; 0x01 stake from seed
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 1)]
        # m1 0x02: topup stake = 200-100 = 100
        # m2 0x01: seed stake = 60-50 = 10 (lower → tried first)
        self._set_topup_allocation([100, 999], [200, 999])
        self.bot._get_quorum = Mock(return_value=['msg'])

        self.bot._phase_full_and_topup(100, [999, 50], [999, 60], digests)

        # m2 (0x01) tried first because stake is lower
        self.bot._deposit_to_module.assert_called_once_with(2)
        self.bot._top_up_to_module.assert_not_called()

    # ─── 0x02 branch ───────────────────────────────────────────

    def test_can_top_up_false_skips_to_next(self):
        # m1 (0x02) can_top_up=False → skipped. m2 (0x01) succeeds.
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 1)]
        self._set_topup_allocation([50, 0], [100, 0])
        self.bot.w3.lido.topup_gateway.can_top_up.return_value = False
        self.bot._get_quorum = Mock(return_value=['msg'])

        # Ensure m1 has lower stake → tried first
        self.bot._phase_full_and_topup(100, [0, 50], [0, 60], digests)

        self.bot._top_up_to_module.assert_not_called()
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_block_distance_not_passed_stops_phase(self):
        digests = [_make_digest(1, '0xA1', 2)]
        self._set_topup_allocation([50], [100])
        self.bot.w3.lido.topup_gateway.is_block_distance_passed.return_value = False

        done, success = self.bot._phase_full_and_topup(100, [0], [0], digests)

        self.assertEqual((True, False), (done, success))
        self.bot._top_up_to_module.assert_not_called()

    def test_routes_0x02_to_top_up_with_topup_allocation(self):
        digests = [_make_digest(1, '0xA1', 2)]
        self._set_topup_allocation([42], [100])  # 42 is the value that must be passed through

        done, success = self.bot._phase_full_and_topup(100, [0], [0], digests)

        self.assertEqual((True, True), (done, success))
        self.bot._top_up_to_module.assert_called_once_with(1, '0xA1', 42)

    # ─── 0x01 branch ───────────────────────────────────────────

    def test_0x01_can_deposit_false_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        self._set_topup_allocation([0, 0], [0, 0])
        self.bot.w3.lido.deposit_security_module.can_deposit.side_effect = lambda mid: mid != 1
        self.bot._get_quorum = Mock(return_value=['msg'])

        # Both 0x01, both have seed alloc. m1 stake = 10, m2 stake = 50 → m1 tried first
        self.bot._phase_full_and_topup(100, [50, 50], [60, 100], digests)
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_0x01_with_quorum_deposits(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self._set_topup_allocation([0], [0])
        self.bot._get_quorum = Mock(return_value=['msg'])

        done, success = self.bot._phase_full_and_topup(100, [50], [100], digests)

        self.assertEqual((True, True), (done, success))
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_0x01_cooldown_active_stops_phase(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self._set_topup_allocation([0], [0])
        # Fresh heartbeat → cooldown active. No quorum.
        self.bot._get_quorum = Mock(return_value=None)

        done, success = self.bot._phase_full_and_topup(100, [50], [100], digests)

        self.assertEqual((True, False), (done, success))
        self.bot._deposit_to_module.assert_not_called()

    def test_0x01_cooldown_expired_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        self._set_topup_allocation([0, 0], [0, 0])
        self._set_cooldown_expired(1)  # m1 expired
        self.bot._get_quorum = Mock(side_effect=lambda mid: ['msg'] if mid == 2 else None)

        # m1 stake 10, m2 stake 50 → m1 first, cooldown expired → next; m2 has quorum
        self.bot._phase_full_and_topup(100, [50, 50], [60, 100], digests)
        self.bot._deposit_to_module.assert_called_once_with(2)

    # ─── Mixed ─────────────────────────────────────────────────

    def test_0x01_skipped_then_0x02_topup(self):
        # m1 (0x01) lower stake but no quorum + cooldown expired → next.
        # m2 (0x02) higher stake → top-up.
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 2)]
        self._set_topup_allocation([0, 50], [0, 200])  # m2 topup stake = 200-50 = 150
        self._set_cooldown_expired(1)
        self.bot._get_quorum = Mock(return_value=None)  # m1 has no quorum

        # m1 seed stake = 60-50 = 10, m2 topup stake = 150 → m1 first
        done, success = self.bot._phase_full_and_topup(100, [50, 999], [60, 999], digests)

        self.assertEqual((True, True), (done, success))
        self.bot._top_up_to_module.assert_called_once_with(2, '0xA2', 50)
        self.bot._deposit_to_module.assert_not_called()


# ─── _execute_actual ───────────────────────────────────────────────


@pytest.fixture
def depositor_bot(
    web3_lido_unit,
    deposit_transaction_sender,
    base_deposit_strategy,
    block_data,
    csm_strategy,
    gas_price_calculator,
):
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as _:
        variables.MESSAGE_TRANSPORTS = ''
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2]
        web3_lido_unit.eth.get_block = Mock(return_value=block_data)
        yield DepositorBot(
            web3_lido_unit, deposit_transaction_sender, base_deposit_strategy, csm_strategy, gas_price_calculator, Mock(), Mock()
        )


@pytest.mark.unit
def test_execute_actual_zero_depositable_ether_short_circuits(depositor_bot):
    """If buffer is empty, skip iteration without computing allocations."""
    depositor_bot._ensure_module_type_cache = Mock()
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=0)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock()
    depositor_bot._phase_seed = Mock()
    depositor_bot._phase_full = Mock()
    depositor_bot._phase_full_and_topup = Mock()

    assert depositor_bot._execute_actual() is False
    depositor_bot.w3.lido.staking_router.get_deposit_allocations.assert_not_called()
    depositor_bot._phase_seed.assert_not_called()
    depositor_bot._phase_full.assert_not_called()
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_phase_a_deposit_short_circuits(depositor_bot):
    """Phase A returns (True, True) → return True, phase B not called."""
    depositor_bot._ensure_module_type_cache = Mock()
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=(True, True))
    depositor_bot._phase_full = Mock()
    depositor_bot._phase_full_and_topup = Mock()

    assert depositor_bot._execute_actual() is True
    depositor_bot._phase_full.assert_not_called()
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_phase_a_failure_does_not_call_phase_b(depositor_bot):
    """Phase A returns (True, False) — e.g. deposit attempt failed — phase B not called."""
    depositor_bot._ensure_module_type_cache = Mock()
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=(True, False))
    depositor_bot._phase_full = Mock()
    depositor_bot._phase_full_and_topup = Mock()

    assert depositor_bot._execute_actual() is False
    depositor_bot._phase_full.assert_not_called()
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_phase_a_cooldown_does_not_call_phase_b(depositor_bot):
    """Same as failure: cooldown returns (True, False) — phase B still not called.
    Documented separately because the algorithm treats cooldown explicitly."""
    depositor_bot._ensure_module_type_cache = Mock()
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=(True, False))
    depositor_bot._phase_full = Mock()
    depositor_bot._phase_full_and_topup = Mock()

    depositor_bot._execute_actual()
    depositor_bot._phase_full.assert_not_called()
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_phase_a_empty_falls_through_to_phase_b(depositor_bot):
    """Phase A returns (False, False) → continue to phase B."""
    variables.ENABLE_TOP_UP = False
    depositor_bot._ensure_module_type_cache = Mock()
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [10, 20], [50, 50]))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=['d1', 'd2'])
    depositor_bot._phase_seed = Mock(return_value=(False, False))
    depositor_bot._phase_full = Mock(return_value=(True, True))

    assert depositor_bot._execute_actual() is True
    # phase_full receives the seed allocations + digests
    depositor_bot._phase_full.assert_called_once_with([10, 20], [50, 50], ['d1', 'd2'])


@pytest.mark.unit
def test_execute_actual_routes_to_phase_full_when_top_up_disabled(depositor_bot):
    variables.ENABLE_TOP_UP = False
    depositor_bot._ensure_module_type_cache = Mock()
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=(False, False))
    depositor_bot._phase_full = Mock(return_value=(False, False))
    depositor_bot._phase_full_and_topup = Mock()

    depositor_bot._execute_actual()
    depositor_bot._phase_full.assert_called_once()
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_routes_to_phase_full_and_topup_when_top_up_enabled(depositor_bot):
    variables.ENABLE_TOP_UP = True
    depositor_bot._ensure_module_type_cache = Mock()
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=(False, False))
    depositor_bot._phase_full = Mock()
    depositor_bot._phase_full_and_topup = Mock(return_value=(False, False))

    depositor_bot._execute_actual()
    depositor_bot._phase_full.assert_not_called()
    depositor_bot._phase_full_and_topup.assert_called_once()


@pytest.mark.unit
def test_execute_actual_both_phases_return_false(depositor_bot):
    variables.ENABLE_TOP_UP = False
    depositor_bot._ensure_module_type_cache = Mock()
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=(False, False))
    depositor_bot._phase_full = Mock(return_value=(False, False))

    assert depositor_bot._execute_actual() is False


# ─── _deposit_to_module ────────────────────────────────────────────


@pytest.mark.unit
def test_deposit_to_module_gas_too_high_returns_false(depositor_bot):
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=False)
    depositor_bot._select_strategy = Mock(return_value=strategy)
    depositor_bot._get_quorum = Mock()
    depositor_bot.prepare_and_send_tx = Mock()

    assert depositor_bot._deposit_to_module(1) is False
    depositor_bot._get_quorum.assert_not_called()
    depositor_bot.prepare_and_send_tx.assert_not_called()


@pytest.mark.unit
def test_deposit_to_module_quorum_disappeared_returns_false(depositor_bot):
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    depositor_bot._select_strategy = Mock(return_value=strategy)
    depositor_bot._get_quorum = Mock(return_value=None)
    depositor_bot.prepare_and_send_tx = Mock()

    assert depositor_bot._deposit_to_module(1) is False
    depositor_bot.prepare_and_send_tx.assert_not_called()


@pytest.mark.unit
def test_deposit_to_module_happy_path_sends_tx(depositor_bot):
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    depositor_bot._select_strategy = Mock(return_value=strategy)
    quorum = ['msg1', 'msg2']
    depositor_bot._get_quorum = Mock(return_value=quorum)
    depositor_bot.prepare_and_send_tx = Mock(return_value=True)

    assert depositor_bot._deposit_to_module(1) is True
    depositor_bot.prepare_and_send_tx.assert_called_once_with(1, quorum)


@pytest.mark.unit
def test_deposit_to_module_csm_strategy_for_csm_module_type(depositor_bot):
    """_select_strategy returns CSM strategy when the module type is MODULE_TYPE_CSM."""
    depositor_bot._module_type_cache[4] = DepositorBot.MODULE_TYPE_CSM
    depositor_bot._csm_strategy.is_gas_price_ok = Mock(return_value=False)
    depositor_bot._general_strategy.is_gas_price_ok = Mock(return_value=False)

    depositor_bot._deposit_to_module(4)

    depositor_bot._csm_strategy.is_gas_price_ok.assert_called_once_with(4)
    depositor_bot._general_strategy.is_gas_price_ok.assert_not_called()


@pytest.mark.unit
def test_deposit_to_module_general_strategy_for_non_csm_module_type(depositor_bot):
    """_select_strategy returns general strategy when the module type is not MODULE_TYPE_CSM."""
    depositor_bot._module_type_cache[1] = b'curated-onchain-v1'.ljust(32, b'\x00')
    depositor_bot._csm_strategy.is_gas_price_ok = Mock(return_value=False)
    depositor_bot._general_strategy.is_gas_price_ok = Mock(return_value=False)

    depositor_bot._deposit_to_module(1)

    depositor_bot._general_strategy.is_gas_price_ok.assert_called_once_with(1)
    depositor_bot._csm_strategy.is_gas_price_ok.assert_not_called()


# ─── _top_up_to_module ─────────────────────────────────────────────


@pytest.mark.unit
def test_top_up_to_module_unknown_type_returns_false(depositor_bot):
    depositor_bot._get_module_type = Mock(return_value=b'unknown-type'.ljust(32, b'\x00'))
    depositor_bot._select_topup_strategy = Mock(return_value=None)

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is False


@pytest.mark.unit
def test_top_up_to_module_gas_too_high_returns_false(depositor_bot):
    depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=False)
    strategy.get_topup_candidates = Mock()
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is False
    strategy.get_topup_candidates.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_no_proof_data_returns_false(depositor_bot):
    depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.get_topup_candidates = Mock(return_value=None)
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)
    depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=10)
    depositor_bot.w3.lido.topup_gateway.top_up = Mock()

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is False
    depositor_bot.w3.lido.topup_gateway.top_up.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    'config_limit,gateway_limit,expected',
    [
        (50, 30, 30),  # gateway is smaller → contract limit wins
        (20, 100, 20),  # config is smaller → variable wins
    ],
)
def test_top_up_to_module_max_validators_uses_min(depositor_bot, config_limit, gateway_limit, expected):
    original = variables.MAX_VALIDATORS_PER_TOP_UP
    variables.MAX_VALIDATORS_PER_TOP_UP = config_limit
    try:
        depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
        strategy = Mock()
        strategy.is_gas_price_ok = Mock(return_value=True)
        strategy.get_topup_candidates = Mock(return_value=['proof'])
        depositor_bot._select_topup_strategy = Mock(return_value=strategy)
        depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=gateway_limit)
        depositor_bot.w3.lido.topup_gateway.top_up = Mock(return_value=Mock())
        depositor_bot.w3.transaction.check = Mock(return_value=True)
        depositor_bot.w3.transaction.send = Mock(return_value=True)

        depositor_bot._top_up_to_module(1, '0xAddr', 50)

        # max_validators is positional arg index 5
        assert strategy.get_topup_candidates.call_args.args[5] == expected
    finally:
        variables.MAX_VALIDATORS_PER_TOP_UP = original


@pytest.mark.unit
def test_top_up_to_module_happy_path_calls_top_up_check_send(depositor_bot):
    proof_data = ['proof']
    tx = Mock(name='tx')

    depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.get_topup_candidates = Mock(return_value=proof_data)
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)
    depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=10)
    depositor_bot.w3.lido.topup_gateway.top_up = Mock(return_value=tx)
    depositor_bot.w3.transaction.check = Mock(return_value=True)
    depositor_bot.w3.transaction.send = Mock(return_value=True)

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is True

    depositor_bot.w3.lido.topup_gateway.top_up.assert_called_once_with(1, proof_data)
    depositor_bot.w3.transaction.check.assert_called_once_with(tx)
    depositor_bot.w3.transaction.send.assert_called_once_with(tx, False, 6)


@pytest.mark.unit
def test_top_up_to_module_passes_module_allocation_through_to_strategy(depositor_bot):
    """The allocation is forwarded to get_topup_candidates, not re-queried."""
    depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.get_topup_candidates = Mock(return_value=['proof'])
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)
    depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=10)
    depositor_bot.w3.lido.topup_gateway.top_up = Mock(return_value=Mock())
    depositor_bot.w3.transaction.check = Mock(return_value=True)
    depositor_bot.w3.transaction.send = Mock(return_value=True)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock()

    depositor_bot._top_up_to_module(7, '0xModule7', 1234)

    # allocation 1234 forwarded; getDepositAllocations NOT re-queried
    assert strategy.get_topup_candidates.call_args.args[4] == 1234
    depositor_bot.w3.lido.staking_router.get_deposit_allocations.assert_not_called()


# ─── _select_topup_strategy / _get_module_type (unchanged) ─────────


@pytest.mark.unit
def test_select_topup_strategy_cmv2_returns_cmv2_strategy(depositor_bot):
    strategy = depositor_bot._select_topup_strategy(DepositorBot.MODULE_TYPE_CMV2)
    assert strategy is depositor_bot._cmv2_topup_strategy


@pytest.mark.unit
def test_select_topup_strategy_unknown_returns_none(depositor_bot):
    unknown_type = b'something-else'.ljust(32, b'\x00')
    assert depositor_bot._select_topup_strategy(unknown_type) is None


@pytest.mark.unit
def test_get_module_type_calls_get_type_on_checksum_address(depositor_bot):
    raw_address = '0xabc1234567890abcdef1234567890abcdef12345'
    checksum_address = '0xAbC1234567890aBcdEf1234567890AbCdEF12345'
    expected_type = b'curated-onchain-v2'.ljust(32, b'\x00')

    depositor_bot.w3.to_checksum_address = Mock(return_value=checksum_address)
    mock_contract = Mock()
    mock_contract.functions.getType.return_value.call.return_value = expected_type
    depositor_bot.w3.eth.contract = Mock(return_value=mock_contract)

    result = depositor_bot._get_module_type(raw_address)

    assert result == expected_type
    depositor_bot.w3.to_checksum_address.assert_called_once_with(raw_address)
    depositor_bot.w3.eth.contract.assert_called_once_with(
        address=checksum_address,
        abi=DepositorBot.GET_TYPE_ABI,
    )
    mock_contract.functions.getType.return_value.call.assert_called_once_with()


# ─── _ensure_module_type_cache ─────────────────────────────────────


@pytest.mark.unit
def test_ensure_module_type_cache_populates_for_whitelisted():
    """Fetches digests and caches the type for every whitelisted module on first call."""
    bot = _make_bot()
    variables.DEPOSIT_MODULES_WHITELIST = [1, 4]
    bot._module_last_heart_beat = {1: datetime.now(), 4: datetime.now()}
    csm_type = DepositorBot.MODULE_TYPE_CSM
    nor_type = b'curated-onchain-v1'.ljust(32, b'\x00')
    bot._get_module_type = Mock(side_effect=lambda addr: csm_type if addr == '0xCSM' else nor_type)
    bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(
        return_value=[_make_digest(1, '0xNOR', 1), _make_digest(4, '0xCSM', 1)]
    )

    bot._ensure_module_type_cache()

    assert bot._module_type_cache[1] == nor_type
    assert bot._module_type_cache[4] == csm_type


@pytest.mark.unit
def test_ensure_module_type_cache_skips_non_whitelisted():
    """Modules not in the whitelist are not cached even if returned by SR."""
    bot = _make_bot()
    variables.DEPOSIT_MODULES_WHITELIST = [1]
    bot._module_last_heart_beat = {1: datetime.now()}
    bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(
        return_value=[_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
    )

    bot._ensure_module_type_cache()

    assert 1 in bot._module_type_cache
    assert 2 not in bot._module_type_cache


@pytest.mark.unit
def test_ensure_module_type_cache_noop_when_all_cached():
    """No RPC call is made when every whitelisted module is already in the cache."""
    bot = _make_bot()
    variables.DEPOSIT_MODULES_WHITELIST = [1, 4]
    bot._module_last_heart_beat = {1: datetime.now(), 4: datetime.now()}
    bot._module_type_cache[1] = DepositorBot.MODULE_TYPE_CMV2
    bot._module_type_cache[4] = DepositorBot.MODULE_TYPE_CSM

    bot._ensure_module_type_cache()

    bot.w3.lido.staking_router.get_all_staking_module_digests.assert_not_called()


# ─── Message actualizer / quorum (unchanged) ───────────────────────


@pytest.fixture
def deposit_message():
    yield {
        'type': 'deposit',
        'depositRoot': '0x64dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b',
        'nonce': 12,
        'blockNumber': 10,
        'blockHash': '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
        'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        'guardianIndex': 8,
        'stakingModuleId': 1,
        'signature': {
            'r': '0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116',
            's': '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0',
            '_vs': '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0',
            'recoveryParam': 0,
            'v': 27,
        },
        'app': {'version': '1.0.3', 'name': 'lido-council-daemon'},
    }


@pytest.fixture
def setup_deposit_message(depositor_bot, block_data):
    depositor_bot.w3.eth.get_block = Mock(return_value=block_data)
    depositor_bot.w3.lido.deposit_contract.get_deposit_root = Mock(
        return_value=b'd\xdc\xf7\nz\xd7\xfck\x1aU\xdbk\x08\xb8n\x9d\x80sbY\x91o\xca\xef\x98\xf4q\x0f\x0b\xach{'
    )
    depositor_bot.w3.lido.staking_router.get_staking_module_nonce = Mock(return_value=12)
    depositor_bot.w3.lido.deposit_security_module.get_guardians = Mock(return_value=['0x43464Fe06c18848a2E2e913194D64c1970f4326a'])


@pytest.mark.unit
def test_depositor_message_actualizer(setup_deposit_message, depositor_bot, deposit_message, block_data):
    message_filter = depositor_bot._get_message_actualize_filter()
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_not_guardian(setup_deposit_message, depositor_bot, deposit_message, block_data):
    depositor_bot.w3.lido.deposit_security_module.get_guardians = Mock(return_value=['0x13464Fe06c18848a2E2e913194D64c1970f4326a'])
    message_filter = depositor_bot._get_message_actualize_filter()
    assert not list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_no_selected_module(setup_deposit_message, depositor_bot, deposit_message, block_data):
    second = deposit_message.copy()
    second['stakingModuleId'] = 2

    message_filter = depositor_bot._get_module_messages_filter(2)
    assert not list(filter(message_filter, [deposit_message]))
    assert len(list(filter(message_filter, [deposit_message, second]))) == 1


@pytest.mark.unit
def test_depositor_message_actualizer_outdated(setup_deposit_message, depositor_bot, deposit_message, block_data):
    deposit_message['blockNumber'] = block_data['number'] - 250
    message_filter = depositor_bot._get_message_actualize_filter()
    assert not list(filter(message_filter, [deposit_message]))

    deposit_message['blockNumber'] = block_data['number'] - 150
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_nonce(setup_deposit_message, depositor_bot, deposit_message, block_data):
    message_filter = depositor_bot._get_module_messages_filter(1)
    assert list(filter(message_filter, [deposit_message]))

    deposit_message['nonce'] -= 10
    assert not list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_root(setup_deposit_message, depositor_bot, deposit_message, block_data):
    deposit_message['depositRoot'] += '0x55dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b'
    message_filter = depositor_bot._get_message_actualize_filter()
    assert not list(filter(message_filter, [deposit_message]))

    deposit_message['blockNumber'] = block_data['number'] + 100
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_get_quorum(depositor_bot, setup_deposit_message):
    deposit_messages = [
        {
            'blockHash': '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
            'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        },
        {
            'blockHash': '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
            'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        },
        {
            'blockHash': '0x232e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
            'guardianAddress': '0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        },
        {
            'blockHash': '0x232e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532',
            'guardianAddress': '0x33464Fe06c18848a2E2e913194D64c1970f4326a',
        },
    ]

    depositor_bot._get_module_messages_filter = Mock(return_value=lambda x: True)
    depositor_bot.w3.lido.deposit_security_module.get_guardian_quorum = Mock(return_value=2)
    depositor_bot.message_storage.get_messages_and_actualize = Mock(return_value=deposit_messages[:2])
    assert not depositor_bot._get_quorum(1)

    depositor_bot.message_storage.get_messages_and_actualize = Mock(return_value=deposit_messages[:4])
    quorum = depositor_bot._get_quorum(1)
    assert quorum
    assert deposit_messages[2] in quorum
    assert deposit_messages[3] in quorum


# ─── Integration ───────────────────────────────────────────────────


@pytest.mark.skip(reason='SR v4 with getDepositAllocations is not deployed on Hoodi yet; re-enable once the upgrade lands.')
@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration,module_id',
    [[{'block': 23647294}, 1]],
    indirect=['web3_provider_integration'],
)
def test_depositor_bot(
    web3_provider_integration,
    web3_lido_integration,
    deposit_transaction_sender_integration,
    base_deposit_strategy_integration,
    gas_price_calculator_integration,
    csm_strategy_integration,
    module_id,
    add_accounts_to_guardian,
):
    variables.DEPOSIT_MODULES_WHITELIST = [1, 2]
    variables.ENABLE_TOP_UP = False

    web3_lido_integration.provider.make_request(
        'anvil_setBalance',
        [
            web3_lido_integration.eth.accounts[0],
            '0x500000000000000000000000',
        ],
    )

    for _ in range(15):
        web3_lido_integration.lido.lido.functions.submit(web3_lido_integration.eth.accounts[0]).transact(
            {
                'from': web3_lido_integration.eth.accounts[0],
                'value': 10000 * 10**18,
            }
        )
    latest = web3_lido_integration.eth.get_block('latest')

    old_module_nonce = web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id)

    deposit_messages = [
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_1, COUNCIL_PK_1, module_id),
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_1, COUNCIL_PK_1, module_id),
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_2, COUNCIL_PK_2, module_id),
    ]

    web3_lido_integration.provider.make_request('anvil_mine', [1])
    web3_lido_integration.lido.staking_router.get_staking_module_ids = Mock(return_value=[module_id])

    db: DepositorBot = DepositorBot(
        web3_lido_integration,
        deposit_transaction_sender_integration,
        base_deposit_strategy_integration,
        csm_strategy_integration,
        gas_price_calculator_integration,
        Mock(),
        Mock(),
    )

    db.message_storage.messages = []
    db.execute(latest)
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce

    db.message_storage.messages = deposit_messages
    assert db.execute(latest)
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce + 1
