import unittest
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import MagicMock, Mock

import pytest
from eth_account import Account
from web3 import Web3
from web3.types import Wei

import variables
from blockchain.contracts.staking_router import MODULE_TYPE_CMV2, MODULE_TYPE_CSM, StakingModuleInfo
from bots.depositor import MESSAGE_BLOCK_WINDOW, DepositorBot, PhaseOutcome, QuorumState, TopUpPath
from cryptography.verify_signature import compute_vs
from tests.conftest import COUNCIL_ADDRESS_1, COUNCIL_ADDRESS_2, COUNCIL_PK_1, COUNCIL_PK_2
from tests.utils.protocol_utils import get_deposit_message

# ─── Shared helpers ────────────────────────────────────────────────


def _make_digest(module_id, address, wc_type, status=0) -> StakingModuleInfo:
    """Build a StakingModuleInfo as produced by the parsing step in _execute_actual."""
    return StakingModuleInfo(module_id=module_id, address=address, wc_type=wc_type, status=status)


def _make_bot(attest_prefix: bytes | None = None):
    """Build a DepositorBot with all-MagicMock deps. No transports → MessageStorage stays empty."""
    variables.MESSAGE_TRANSPORTS = ''
    w3 = MagicMock()
    # w3.lido is a MagicMock, so `delegation` would auto-create a truthy child and silently turn on
    # delegated top-up execution. Default to the direct-call configuration; tests that exercise
    # delegation set it explicitly.
    w3.lido.delegation = None
    if attest_prefix is not None:
        w3.lido.deposit_security_module.get_attest_message_prefix.return_value = attest_prefix
        w3.lido.guardian_delegation_active.return_value = False
    # Skip the real ConsolidationBus backfill (needs RPC) — inject a mock indexer so top-up paths
    # are still exercised. ENABLE_TOP_UP is left untouched; tests set it as needed.
    with mock.patch.object(DepositorBot, '_build_consolidation_indexer', return_value=MagicMock()):
        bot = DepositorBot(
            w3=w3,
            sender=MagicMock(),
            base_deposit_strategy=MagicMock(),
            csm_strategy=MagicMock(),
            gas_price_calculator=MagicMock(),
            keys_api=MagicMock(),
            cl=MagicMock(),
        )
    return bot


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

    def test_quorum_last_seen_metric_updated_on_truthy_quorum(self):
        self.bot._get_quorum = Mock(return_value=['msg'])
        self.bot._select_strategy = Mock(return_value=Mock())

        with mock.patch('bots.depositor.MODULE_QUORUM_LAST_SEEN_TIMESTAMP') as gauge:
            self.bot._refresh_modules_state()

        called_ids = sorted(c.args[0] for c in gauge.labels.call_args_list)
        self.assertEqual([1, 2, 3], called_ids)
        gauge.labels.return_value.set.assert_called()

    def test_quorum_last_seen_metric_not_updated_on_none_quorum(self):
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._select_strategy = Mock(return_value=Mock())

        with mock.patch('bots.depositor.MODULE_QUORUM_LAST_SEEN_TIMESTAMP') as gauge:
            self.bot._refresh_modules_state()

        gauge.labels.assert_not_called()

    def test_quorum_state_metric_updated_for_every_whitelisted_module(self):
        """Regression: QUORUM_STATE used to be set only inside _try_deposit's call path
        (_resolve_quorum), so a module never reached in a given cycle (top-up-only cycle, lost the
        priority race, zero allocation) left it stale. _refresh_modules_state must touch it for
        every whitelisted module every cycle, regardless of whether it has quorum."""
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._select_strategy = Mock(return_value=Mock())

        with mock.patch('bots.depositor.QUORUM_STATE') as quorum_state:
            self.bot._refresh_modules_state()

        called_ids = sorted(c.args[0] for c in quorum_state.labels.call_args_list)
        self.assertEqual([1, 2, 3], called_ids)
        quorum_state.labels.return_value.state.assert_called()

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


# ─── _resolve_quorum ───────────────────────────────────────────────


@pytest.mark.unit
class TestResolveQuorum(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1]

    def test_ready_when_quorum_present(self):
        self.bot._get_quorum = Mock(return_value=['msg'])
        self.assertIs(QuorumState.READY, self.bot._resolve_quorum(1))

    def test_retained_when_no_quorum_but_recent(self):
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=1)
        self.assertIs(QuorumState.RETAINED, self.bot._resolve_quorum(1))

    def test_stale_when_no_quorum_and_window_expired(self):
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)
        self.assertIs(QuorumState.STALE, self.bot._resolve_quorum(1))

    def test_retained_at_boundary(self):
        # The window is `<=` — exactly at the boundary still counts as retained.
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES, seconds=-1)
        self.assertIs(QuorumState.RETAINED, self.bot._resolve_quorum(1))

    def test_reports_state_via_enum_metric_not_a_numeric_gauge(self):
        """QUORUM_STATE is a prometheus_client.Enum — driven with .state(<QuorumState member>),
        never .set(<int>). A regression here would silently produce a numeric-again series."""
        self.bot._get_quorum = Mock(return_value=['msg'])

        with mock.patch('bots.depositor.QUORUM_STATE') as quorum_state:
            self.bot._resolve_quorum(1)

        quorum_state.labels.assert_called_once_with(1)
        quorum_state.labels.return_value.state.assert_called_once_with(QuorumState.READY)
        quorum_state.labels.return_value.set.assert_not_called()


# ─── _common_preconditions ─────────────────────────────────────────


@pytest.mark.unit
class TestCommonPreconditions(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        self.bot.w3.lido.lido.can_deposit = Mock(return_value=True)
        self.bot.w3.lido.deposit_security_module.get_guardian_quorum = Mock(return_value=1)

    def test_passes_when_all_ok(self):
        self.assertTrue(self.bot._common_preconditions())

    def test_fails_when_lido_cannot_deposit(self):
        self.bot.w3.lido.lido.can_deposit = Mock(return_value=False)
        self.assertFalse(self.bot._common_preconditions())

    def test_fails_when_quorum_zero(self):
        self.bot.w3.lido.deposit_security_module.get_guardian_quorum = Mock(return_value=0)
        self.assertFalse(self.bot._common_preconditions())


# ─── _publish_allocation_metrics ─────────────────────────────────────


@pytest.mark.unit
class TestPublishAllocationMetrics(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2]

    def test_publishes_allocation_and_stake_for_whitelisted_modules(self):
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 1)]

        with mock.patch('bots.depositor.MODULE_ALLOCATION') as allocation, mock.patch('bots.depositor.MODULE_STAKE') as stake:
            self.bot._publish_allocation_metrics(digests, [30, 0], [100, 0], 'seed')

        allocation.labels.assert_any_call(1, 'seed')
        allocation.labels.assert_any_call(2, 'seed')
        allocation.labels.return_value.set.assert_any_call(30)
        allocation.labels.return_value.set.assert_any_call(0)
        stake.labels.return_value.set.assert_any_call(70)  # 100 - 30

    def test_skips_non_whitelisted_modules(self):
        # Regression: a module excluded here would otherwise show a stale outcome from its last
        # successful cycle, misrepresenting why it currently isn't a deposit candidate.
        variables.DEPOSIT_MODULES_WHITELIST = [1]
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 1)]

        with mock.patch('bots.depositor.MODULE_ALLOCATION') as allocation:
            self.bot._publish_allocation_metrics(digests, [30, 999], [100, 999], 'seed')

        called_ids = {c.args[0] for c in allocation.labels.call_args_list}
        self.assertEqual({1}, called_ids)

    def test_publishes_zero_allocation_for_excluded_module(self):
        """A module with zero allocation must still get a fresh 0 this cycle, not be left alone."""
        digests = [_make_digest(1, '0xA1', 2)]

        with mock.patch('bots.depositor.MODULE_ALLOCATION') as allocation:
            self.bot._publish_allocation_metrics(digests, [0], [0], 'seed')

        allocation.labels.assert_called_once_with(1, 'seed')
        allocation.labels.return_value.set.assert_called_once_with(0)


# ─── _collect_candidates ───────────────────────────────────────────


@pytest.mark.unit
class TestCollectCandidates(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]

    def test_filters_by_wc_type(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 2)]
        cands = self.bot._collect_candidates(digests, 2, [50, 50], [100, 100])
        self.assertEqual([2], [c.module_id for c in cands])

    def test_filters_non_whitelisted(self):
        variables.DEPOSIT_MODULES_WHITELIST = [1]
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        cands = self.bot._collect_candidates(digests, 1, [50, 50], [100, 100])
        self.assertEqual([1], [c.module_id for c in cands])

    def test_filters_zero_allocation(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        cands = self.bot._collect_candidates(digests, 1, [0, 50], [0, 100])
        self.assertEqual([2], [c.module_id for c in cands])

    def test_filters_inactive_status(self):
        # status: 0=Active (kept), 1=DepositsPaused, 2=Stopped (both skipped)
        digests = [_make_digest(1, '0xA1', 1, status=1), _make_digest(2, '0xA2', 1, status=0), _make_digest(3, '0xA3', 1, status=2)]
        cands = self.bot._collect_candidates(digests, 1, [50, 50, 50], [100, 100, 100])
        self.assertEqual([2], [c.module_id for c in cands])

    def test_builds_fields_and_stake(self):
        digests = [_make_digest(1, '0xA1', 2)]
        cands = self.bot._collect_candidates(digests, 2, [30], [100])
        c = cands[0]
        self.assertEqual((c.digest_index, c.module_id, c.wc_type, c.address), (0, 1, 2, '0xA1'))
        self.assertEqual(c.stake, 70)  # new - allocated = 100 - 30
        self.assertEqual(c.allocation, 30)  # allocated[i]

    def test_preserves_digest_order_without_sorting(self):
        # the method does not sort; index mirrors digest position
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1), _make_digest(3, '0xA3', 1)]
        cands = self.bot._collect_candidates(digests, 1, [10, 20, 30], [110, 70, 80])
        self.assertEqual([0, 1, 2], [c.digest_index for c in cands])
        self.assertEqual([1, 2, 3], [c.module_id for c in cands])


# ─── _phase_seed ───────────────────────────────────────────────────


@pytest.mark.unit
class TestPhaseSeed(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        # Fresh heartbeats → all modules are in cooldown by default.
        self.bot._module_last_heart_beat = {m: datetime.now() for m in [1, 2, 3]}
        # self.bot._get_quorum = Mock(return_value=None)
        # self.bot._deposit_to_module = Mock(return_value=True)

    def _set_cooldown_expired(self, module_id):
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    # ─── Filters ───────────────────────────────────────────────

    def test_filters_non_0x02(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        outcome = self.bot._phase_seed([50], [100], digests)
        self.assertEqual(PhaseOutcome.SKIPPED, outcome)
        self.bot._deposit_to_module.assert_not_called()

    def test_filters_zero_allocation(self):
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=['msg'])
        # module 1: allocated=0 → skipped; module 2: allocated=50 → deposits
        self.bot._phase_seed([0, 50], [0, 100], digests)
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_filters_non_whitelisted(self):
        digests = [_make_digest(4, '0xA4', 2)]
        self.bot._deposit_to_module = Mock(return_value=True)
        outcome = self.bot._phase_seed([50], [100], digests)
        self.assertEqual(PhaseOutcome.SKIPPED, outcome)
        self.bot._deposit_to_module.assert_not_called()

    # ─── Sort & selection ──────────────────────────────────────

    def test_sorts_by_stake_asc(self):
        self.bot._deposit_to_module = Mock(return_value=True)
        # stake = new - allocated. Lowest stake first.
        # m1: 110-10=100; m2: 70-50=20 (lowest); m3: 80-30=50
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2), _make_digest(3, '0xA3', 2)]
        self.bot._get_quorum = Mock(return_value=['msg'])

        outcome = self.bot._phase_seed([10, 50, 30], [110, 70, 80], digests)

        self.assertEqual(PhaseOutcome.SENT, outcome)
        # Lowest-stake module (id=2) is tried first.
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_index_alignment_with_subset_whitelist(self):
        # SR returns 4 modules; WHITELIST = [1, 3]. Allocations are indexed by SR list.
        variables.DEPOSIT_MODULES_WHITELIST = [1, 3]
        self.bot._deposit_to_module = Mock(return_value=True)
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
        outcome = self.bot._phase_seed([], [], [])
        self.assertEqual(PhaseOutcome.SKIPPED, outcome)

    # ─── Iteration ─────────────────────────────────────────────

    def test_single_with_quorum_deposits(self):
        self.bot._deposit_to_module = Mock(return_value=True)
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._get_quorum = Mock(return_value=['msg'])

        outcome = self.bot._phase_seed([50], [100], digests)

        self.assertEqual(PhaseOutcome.SENT, outcome)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_cooldown_active_no_quorum_stops_phase(self):
        self.bot._deposit_to_module = Mock(return_value=True)
        # Retention active (fresh heartbeat) + no quorum → stop phase, don't proceed.
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._get_quorum = Mock(return_value=None)

        outcome = self.bot._phase_seed([50], [100], digests)

        self.assertEqual(PhaseOutcome.WAIT_QUORUM, outcome)
        self.bot._deposit_to_module.assert_not_called()

    def test_cooldown_expired_no_quorum_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2)]
        self.bot._deposit_to_module = Mock(return_value=True)
        # m2 lower stake (tried first), cooldown expired → next; m1 has quorum
        self._set_cooldown_expired(2)
        self.bot._get_quorum = Mock(side_effect=lambda module_id: ['msg'] if module_id == 1 else None)

        self.bot._phase_seed([10, 50], [110, 70], digests)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_all_cooldowns_expired_returns_done_false(self):
        self.bot._deposit_to_module = Mock(return_value=True)
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2)]
        self._set_cooldown_expired(1)
        self._set_cooldown_expired(2)
        self.bot._get_quorum = Mock(return_value=None)

        outcome = self.bot._phase_seed([30, 50], [50, 100], digests)

        self.assertEqual(PhaseOutcome.SKIPPED, outcome)
        self.bot._deposit_to_module.assert_not_called()

    def test_deposit_failure_still_returns_done_true(self):
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._get_quorum = Mock(return_value=['msg'])
        self.bot._deposit_to_module = Mock(return_value=False)

        outcome = self.bot._phase_seed([50], [100], digests)

        self.assertEqual(PhaseOutcome.TX_FAILED, outcome)  # deposit attempted, tx failed

    # ─── distance cooldown ─────────────────────────────────────

    def test_distance_not_passed_waits(self):
        # min deposit distance not passed → wait, don't divert.
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot.w3.lido.deposit_security_module.is_min_deposit_distance_passed = Mock(return_value=False)
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=['msg'])  # quorum exists — to prove we return before checking it

        outcome = self.bot._phase_seed([50], [100], digests)

        self.assertEqual(PhaseOutcome.WAIT_DISTANCE, outcome)  # no fall-through to Phase B
        self.bot._deposit_to_module.assert_not_called()
        self.bot._get_quorum.assert_not_called()

    def test_distance_block_on_priority_does_not_divert(self):
        # Priority (lowest-stake) module 2 is distance-blocked → wait for it; do NOT deposit lower-priority module 1.
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 2)]
        self.bot.w3.lido.deposit_security_module.is_min_deposit_distance_passed = Mock(side_effect=lambda module_id: module_id != 2)
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=['msg'])
        # m1 stake = 110-10 = 100; m2 stake = 70-50 = 20 (lowest → tried first)
        outcome = self.bot._phase_seed([10, 50], [110, 70], digests)

        self.assertEqual(PhaseOutcome.WAIT_DISTANCE, outcome)
        self.bot._deposit_to_module.assert_not_called()


@pytest.mark.unit
class TestPhaseFull(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        self.bot._module_last_heart_beat = {m: datetime.now() for m in [1, 2, 3]}
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._deposit_to_module = Mock(return_value=True)

    def _set_cooldown_expired(self, module_id):
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    def test_filters_non_0x01(self):
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._deposit_to_module = Mock(return_value=True)
        outcome = self.bot._phase_full_and_topup(Wei(0), [50], [100], digests)
        self.assertEqual(PhaseOutcome.SKIPPED, outcome)
        self.bot._deposit_to_module.assert_not_called()

    def test_filters_zero_seed_allocation(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=['msg'])
        self.bot._phase_full_and_topup(Wei(0), [0, 50], [0, 100], digests)
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_filters_non_whitelisted(self):
        digests = [_make_digest(4, '0xA4', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        outcome = self.bot._phase_full_and_topup(Wei(0), [50], [100], digests)
        self.assertEqual(PhaseOutcome.SKIPPED, outcome)
        self.bot._deposit_to_module.assert_not_called()

    def test_sorts_by_stake_asc(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1), _make_digest(3, '0xA3', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=['msg'])
        # m2 stake = 70-50 = 20 (lowest)
        self.bot._phase_full_and_topup(Wei(0), [10, 50, 30], [110, 70, 80], digests)
        self.bot._deposit_to_module.assert_called_once_with(2)

    def test_quorum_active_deposits(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=['msg'])

        outcome = self.bot._phase_full_and_topup(Wei(0), [50], [100], digests)

        self.assertEqual(PhaseOutcome.SENT, outcome)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_cooldown_active_stops_phase(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=None)

        outcome = self.bot._phase_full_and_topup(Wei(0), [50], [100], digests)

        self.assertEqual(PhaseOutcome.WAIT_QUORUM, outcome)
        self.bot._deposit_to_module.assert_not_called()

    def test_cooldown_expired_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        self._set_cooldown_expired(2)
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(side_effect=lambda module_id: ['msg'] if module_id == 1 else None)

        self.bot._phase_full_and_topup(Wei(0), [10, 50], [110, 70], digests)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_empty_digests_returns_done_false(self):
        outcome = self.bot._phase_full_and_topup(Wei(0), [], [], [])
        self.assertEqual(PhaseOutcome.SKIPPED, outcome)

    # ─── distance cooldown ─────────────────────────────────────

    def test_distance_not_passed_waits(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self.bot.w3.lido.deposit_security_module.is_min_deposit_distance_passed = Mock(return_value=False)
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=['msg'])

        outcome = self.bot._phase_full_and_topup(Wei(0), [50], [100], digests)

        self.assertEqual(PhaseOutcome.WAIT_DISTANCE, outcome)
        self.bot._deposit_to_module.assert_not_called()
        self.bot._get_quorum.assert_not_called()


# ─── _phase_full_and_topup ─────────────────────────────────────────


@pytest.mark.unit
class TestPhaseFullAndTopup(unittest.TestCase):
    def setUp(self):
        self.bot = _make_bot()
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        self.bot._module_last_heart_beat = {m: datetime.now() for m in [1, 2, 3]}
        self.bot.w3.lido.topup_gateway.is_block_distance_passed = Mock(return_value=True)
        self.bot._get_quorum = Mock(return_value=None)
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)

    def _set_cooldown_expired(self, module_id):
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    def _set_topup_allocation(self, allocated, new):
        """Stub get_deposit_allocations(is_top_up=True) → (total, allocated, new)."""
        # new - already allocated + allocation sum at current allocation
        sum_allocated = sum(n - a for n, a in zip(new, allocated, strict=True))
        self.bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(sum_allocated, allocated, new))

    # ─── Filters ───────────────────────────────────────────────

    def test_filters_non_whitelisted(self):
        variables.DEPOSIT_MODULES_WHITELIST = [1]
        digests = [_make_digest(2, '0xA2', 2), _make_digest(3, '0xA3', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self._set_topup_allocation([50, 50], [100, 100])
        outcome = self.bot._phase_full_and_topup(Wei(100), [0, 50], [0, 100], digests, top_up_enabled=True)
        self.assertEqual(PhaseOutcome.SKIPPED, outcome)
        self.bot._top_up_to_module.assert_not_called()
        self.bot._deposit_to_module.assert_not_called()

    def test_filters_zero_allocation_per_type(self):
        # 0x02 → check topup_allocated; 0x01 → check seed_allocated
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        # 0x02 m1: topup=0 → skipped; 0x01 m2: seed=0 → skipped
        self._set_topup_allocation([0, 0], [50, 100])
        self.bot._get_quorum = Mock(return_value=['msg'])

        outcome = self.bot._phase_full_and_topup(Wei(1000), [0, 0], [50, 100], digests, top_up_enabled=True)

        self.assertEqual(PhaseOutcome.SKIPPED, outcome)
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
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        # lowest stake is 2 but it is not whitlisted
        self._set_topup_allocation([70, 10, 999, 999], [90, 13, 1050, 1050])
        self.bot._get_quorum = Mock(return_value=['msg'])

        self.bot._phase_full_and_topup(Wei(100), [50, 999, 999, 999], [70, 1002, 1050, 1050], digests, top_up_enabled=True)

        # m1 (0x02) goes first
        self.bot._top_up_to_module.assert_called_once_with(1, '0xA1', 70)
        self.bot._deposit_to_module.assert_not_called()

    def test_sorts_by_per_type_stake_asc(self):
        # 0x02 stake from topup; 0x01 stake from seed
        digests = [_make_digest(1, '0xA1', 2), _make_digest(2, '0xA2', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        # m1 0x02: topup stake = 200-100 = 100
        # m2 0x01: seed stake = 60-50 = 10 (lower → tried first)
        self._set_topup_allocation([100, 999], [200, 999])
        self.bot._get_quorum = Mock(return_value=['msg'])

        self.bot._phase_full_and_topup(Wei(100), [999, 50], [999, 60], digests, top_up_enabled=True)

        # m2 (0x01) tried first because stake is lower
        self.bot._deposit_to_module.assert_called_once_with(2)
        self.bot._top_up_to_module.assert_not_called()

    # ─── 0x02 branch ───────────────────────────────────────────

    def test_block_distance_not_passed_stops_phase(self):
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self._set_topup_allocation([50], [100])
        self.bot.w3.lido.topup_gateway.is_block_distance_passed = Mock(return_value=False)

        outcome = self.bot._phase_full_and_topup(Wei(100), [0], [0], digests, top_up_enabled=True)

        self.assertEqual(PhaseOutcome.WAIT_DISTANCE, outcome)
        self.bot._top_up_to_module.assert_not_called()

    def test_routes_0x02_to_top_up_with_topup_allocation(self):
        digests = [_make_digest(1, '0xA1', 2)]
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self._set_topup_allocation([42], [100])  # 42 is the value that must be passed through

        outcome = self.bot._phase_full_and_topup(Wei(100), [0], [0], digests, top_up_enabled=True)

        self.assertEqual(PhaseOutcome.SENT, outcome)
        self.bot._top_up_to_module.assert_called_once_with(1, '0xA1', 42)

    # ─── 0x01 branch ───────────────────────────────────────────

    def test_0x01_with_quorum_deposits(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self._set_topup_allocation([0], [0])
        self.bot._get_quorum = Mock(return_value=['msg'])

        outcome = self.bot._phase_full_and_topup(Wei(100), [50], [100], digests, top_up_enabled=True)

        self.assertEqual(PhaseOutcome.SENT, outcome)
        self.bot._deposit_to_module.assert_called_once_with(1)

    def test_0x01_cooldown_active_stops_phase(self):
        digests = [_make_digest(1, '0xA1', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self._set_topup_allocation([0], [0])
        # Fresh heartbeat → cooldown active. No quorum.
        self.bot._get_quorum = Mock(return_value=None)

        outcome = self.bot._phase_full_and_topup(Wei(100), [50], [100], digests, top_up_enabled=True)

        self.assertEqual(PhaseOutcome.WAIT_QUORUM, outcome)
        self.bot._deposit_to_module.assert_not_called()

    def test_0x01_cooldown_expired_moves_to_next(self):
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 1)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self._set_topup_allocation([0, 0], [0, 0])
        self._set_cooldown_expired(1)  # m1 expired
        self.bot._get_quorum = Mock(side_effect=lambda module_id: ['msg'] if module_id == 2 else None)

        # m1 stake 10, m2 stake 50 → m1 first, cooldown expired → next; m2 has quorum
        self.bot._phase_full_and_topup(Wei(100), [50, 50], [60, 100], digests, top_up_enabled=True)
        self.bot._deposit_to_module.assert_called_once_with(2)

    # ─── Mixed ─────────────────────────────────────────────────

    def test_0x01_skipped_then_0x02_topup(self):
        # m1 (0x01) lower stake but no quorum + cooldown expired → next.
        # m2 (0x02) higher stake → top-up.
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 2)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self._set_topup_allocation([0, 50], [0, 200])  # m2 topup stake = 200-50 = 150
        self._set_cooldown_expired(1)
        self.bot._get_quorum = Mock(return_value=None)  # m1 has no quorum

        # m1 seed stake = 60-50 = 10, m2 topup stake = 150 → m1 first
        outcome = self.bot._phase_full_and_topup(Wei(100), [50, 999], [60, 999], digests, top_up_enabled=True)

        self.assertEqual(PhaseOutcome.SENT, outcome)
        self.bot._top_up_to_module.assert_called_once_with(2, '0xA2', 50)
        self.bot._deposit_to_module.assert_not_called()

    # ─── distance cooldown ─────────────────────────────────────

    def test_deposits_paused_skips_0x01_keeps_topup(self):
        # deposits_paused=True → 0x01 full deposits are not collected; 0x02 top-up still happens.
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 2)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self._set_topup_allocation([999, 50], [999, 200])  # m2 0x02 is a top-up candidate
        self.bot._get_quorum = Mock(return_value=['msg'])  # m1 0x01 would deposit if collected

        outcome = self.bot._phase_full_and_topup(Wei(100), [50, 999], [60, 999], digests, deposits_paused=True, top_up_enabled=True)

        self.assertEqual(PhaseOutcome.SENT, outcome)
        self.bot._top_up_to_module.assert_called_once_with(2, '0xA2', 50)
        self.bot._deposit_to_module.assert_not_called()

    def test_deposits_paused_and_topup_disabled_skips_all(self):
        # deposits_paused=True AND top_up_enabled=False → neither 0x01 nor 0x02 collected → SKIPPED, no-op.
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 2)]
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self.bot._get_quorum = Mock(return_value=['msg'])  # would deposit if 0x01 were collected

        outcome = self.bot._phase_full_and_topup(Wei(100), [50, 50], [60, 60], digests, deposits_paused=True, top_up_enabled=False)

        self.assertEqual(PhaseOutcome.SKIPPED, outcome)
        self.bot._deposit_to_module.assert_not_called()
        self.bot._top_up_to_module.assert_not_called()

    def test_0x01_distance_block_does_not_divert_to_topup(self):
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        # Priority 0x01 module is distance-blocked → wait for it; do NOT divert to the ready 0x02 top-up.
        digests = [_make_digest(1, '0xA1', 1), _make_digest(2, '0xA2', 2)]
        self._set_topup_allocation([999, 50], [999, 200])  # m2 0x02 topup stake = 150
        self.bot.w3.lido.deposit_security_module.is_min_deposit_distance_passed = Mock(return_value=False)
        # m1 0x01 seed stake = 60-50 = 10 (lowest → tried first), m2 topup stake = 150
        outcome = self.bot._phase_full_and_topup(Wei(100), [50, 999], [60, 999], digests, top_up_enabled=True)

        self.assertEqual(PhaseOutcome.WAIT_DISTANCE, outcome)
        self.bot._deposit_to_module.assert_not_called()
        self.bot._top_up_to_module.assert_not_called()


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
        # w3.lido is a Mock, so `delegation` would auto-create a truthy child and silently turn on
        # delegated execution. Default to the direct-call configuration; tests that need delegation
        # set it explicitly. Must be set before construction — startup validation reads it.
        web3_lido_unit.lido.delegation = None
        # Skip the real ConsolidationBus backfill (needs RPC) — inject a mock indexer.
        with mock.patch.object(DepositorBot, '_build_consolidation_indexer', return_value=MagicMock()):
            bot = DepositorBot(
                web3_lido_unit, deposit_transaction_sender, base_deposit_strategy, csm_strategy, gas_price_calculator, Mock(), Mock()
            )
        bot.w3.lido.deposit_security_module.is_deposits_paused = Mock(return_value=False)
        bot.w3.lido.topup_gateway.is_paused = Mock(return_value=False)
        yield bot


@pytest.mark.unit
def test_execute_actual_zero_depositable_ether_short_circuits(depositor_bot):
    """If buffer is empty, skip iteration without computing allocations."""
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=0)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock()
    depositor_bot._phase_seed = Mock()
    depositor_bot._phase_full_and_topup = Mock()

    assert depositor_bot._execute_actual() is False
    depositor_bot.w3.lido.staking_router.get_deposit_allocations.assert_not_called()
    depositor_bot._phase_seed.assert_not_called()
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_reports_depositable_ether_even_when_zero(depositor_bot):
    """DEPOSITABLE_ETHER must stay current even on the empty-buffer short-circuit — it's the
    first thing worth checking when asking why nothing is being deposited."""
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=0)

    with mock.patch('bots.depositor.DEPOSITABLE_ETHER') as gauge:
        depositor_bot._execute_actual()

    gauge.set.assert_called_once_with(0)


@pytest.mark.unit
def test_execute_actual_refreshes_topup_path_on_empty_buffer(depositor_bot):
    """The empty buffer is the common idle state, so resolving the path after that early return
    would pin `topup_execution_path` at its last value while a delegate rotation, revocation or
    termination goes unnoticed — the exact failure the metric exists to surface."""
    variables.ENABLE_TOP_UP = True
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=0)
    depositor_bot._resolve_topup_path = Mock(return_value=TopUpPath.NOT_DELEGATE)

    with mock.patch('bots.depositor.TOPUP_EXECUTION_PATH') as metric:
        assert depositor_bot._execute_actual() is False

    depositor_bot._resolve_topup_path.assert_called_once()
    metric.state.assert_called_once_with(TopUpPath.NOT_DELEGATE)
    assert depositor_bot._topup_path is TopUpPath.NOT_DELEGATE


@pytest.mark.unit
def test_execute_actual_refreshes_topup_path_when_phase_a_short_circuits(depositor_bot):
    """Same reason, for the other early return: a Phase A deposit ends the iteration before Phase B."""
    variables.ENABLE_TOP_UP = True
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.SENT)
    depositor_bot._phase_full_and_topup = Mock()
    depositor_bot._resolve_topup_path = Mock(return_value=TopUpPath.TERMINATED)

    assert depositor_bot._execute_actual() is True
    depositor_bot._phase_full_and_topup.assert_not_called()
    depositor_bot._resolve_topup_path.assert_called_once()
    assert depositor_bot._topup_path is TopUpPath.TERMINATED


@pytest.mark.unit
def test_execute_actual_phase_a_deposit_short_circuits(depositor_bot):
    """Phase A SENT → _execute_actual returns backoff=True, phase B not called."""
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.SENT)
    depositor_bot._phase_full_and_topup = Mock()

    assert depositor_bot._execute_actual() is True
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_phase_a_failure_does_not_call_phase_b(depositor_bot):
    """Phase A returns TX_FAILED → no backoff (False), phase B not called."""
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.TX_FAILED)
    depositor_bot._phase_full_and_topup = Mock()

    assert depositor_bot._execute_actual() is False
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_phase_a_cooldown_does_not_call_phase_b(depositor_bot):
    """Quorum-retention wait (WAIT_QUORUM) is non-SKIPPED → phase B still not called."""
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.WAIT_QUORUM)
    depositor_bot._phase_full_and_topup = Mock()

    depositor_bot._execute_actual()
    depositor_bot._phase_full_and_topup.assert_not_called()


@pytest.mark.unit
def test_execute_actual_phase_a_empty_falls_through_to_phase_b(depositor_bot):
    """Phase A SKIPPED → continue to phase B."""
    variables.ENABLE_TOP_UP = False
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [10, 20], [50, 50]))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.SKIPPED)
    depositor_bot._phase_full_and_topup = Mock(return_value=PhaseOutcome.SENT)

    assert depositor_bot._execute_actual() is True
    # phase B receives depositable ether, seed allocations, parsed (empty) digests, and the gate flags
    depositor_bot._phase_full_and_topup.assert_called_once_with(100, [10, 20], [50, 50], [], False, False)


@pytest.mark.unit
def test_execute_actual_top_up_disabled_gates_topup_off(depositor_bot):
    variables.ENABLE_TOP_UP = False
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.SKIPPED)
    depositor_bot._phase_full_and_topup = Mock(return_value=PhaseOutcome.SKIPPED)

    depositor_bot._execute_actual()
    depositor_bot._phase_full_and_topup.assert_called_once()
    assert depositor_bot._phase_full_and_topup.call_args.args[-1] is False  # top_up_enabled


@pytest.mark.unit
def test_execute_actual_routes_to_phase_full_and_topup_when_top_up_enabled(depositor_bot):
    variables.ENABLE_TOP_UP = True
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.SKIPPED)
    depositor_bot._phase_full_and_topup = Mock(return_value=PhaseOutcome.SKIPPED)

    depositor_bot._execute_actual()
    depositor_bot._phase_full_and_topup.assert_called_once()


@pytest.mark.unit
def test_execute_actual_top_up_gateway_paused_gates_topup_off(depositor_bot):
    """ENABLE_TOP_UP on but TopUpGateway paused → top-ups disabled this iteration (top_up_enabled=False)."""
    variables.ENABLE_TOP_UP = True
    depositor_bot.w3.lido.topup_gateway.is_paused = Mock(return_value=True)
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.SKIPPED)
    depositor_bot._phase_full_and_topup = Mock(return_value=PhaseOutcome.SKIPPED)

    depositor_bot._execute_actual()
    depositor_bot._phase_full_and_topup.assert_called_once()
    assert depositor_bot._phase_full_and_topup.call_args.args[-1] is False  # top_up_enabled (gateway paused)


@pytest.mark.unit
def test_execute_actual_deposits_paused_skips_phase_a_and_passes_flag(depositor_bot):
    """Deposits paused → Phase A (seed deposits) skipped; Phase B runs with deposits_paused=True (top-ups only)."""
    variables.ENABLE_TOP_UP = True
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.deposit_security_module.is_deposits_paused = Mock(return_value=True)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock()
    depositor_bot._phase_full_and_topup = Mock(return_value=PhaseOutcome.SKIPPED)

    depositor_bot._execute_actual()

    depositor_bot._phase_seed.assert_not_called()  # Phase A is deposits-only → skipped while paused
    depositor_bot._phase_full_and_topup.assert_called_once()
    assert depositor_bot._phase_full_and_topup.call_args.args[4] is True  # deposits_paused flag


@pytest.mark.unit
def test_execute_actual_both_phases_return_false(depositor_bot):
    variables.ENABLE_TOP_UP = False
    depositor_bot._refresh_modules_state = Mock()
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot._phase_seed = Mock(return_value=PhaseOutcome.SKIPPED)

    assert depositor_bot._execute_actual() is False


@pytest.mark.unit
class TestExecuteActualScheduling(unittest.TestCase):
    def setUp(self):
        variables.ENABLE_TOP_UP = True
        variables.DEPOSIT_MODULES_WHITELIST = [5, 1]
        self.bot = _make_bot()
        self.bot._refresh_modules_state = Mock()
        self.bot._common_preconditions = Mock(return_value=True)
        self.bot.w3.lido.deposit_security_module.is_deposits_paused = Mock(return_value=False)
        self.bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self.bot.w3.lido.deposit_security_module.is_min_deposit_distance_passed = Mock(return_value=True)
        self.bot.w3.lido.topup_gateway.is_block_distance_passed = Mock(return_value=True)
        self.bot.w3.lido.topup_gateway.is_paused = Mock(return_value=False)
        self.bot._get_quorum = Mock(return_value=['msg'])
        # heartbeats fresh → quorum-retention cooldown active by default
        self.bot._module_last_heart_beat = {5: datetime.now(), 1: datetime.now()}
        # digests: index 0 = m5 (0x02, active), index 1 = m1 (0x01, active)
        self.bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(
            return_value=[_make_digest(5, '0x5', 2), _make_digest(1, '0x1', 1)]
        )

    def _set_alloc(self, seed, topup):
        """Per-digest-index allocations; `new` = allocated + 1000 so stake is non-zero."""

        def alloc(_amount, is_top_up):
            src = topup if is_top_up else seed
            return (0, list(src), [v + 1000 for v in src])

        self.bot.w3.lido.staking_router.get_deposit_allocations = Mock(side_effect=alloc)

    def _stale_quorum(self, module_id):
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    # ─── A. deposit candidate (Phase A seed 0x02) ──────────────

    def test_A1_deposit_distance_not_passed(self):
        self._set_alloc(seed=[100, 0], topup=[0, 0])
        self.bot.w3.lido.deposit_security_module.is_min_deposit_distance_passed = Mock(return_value=False)
        self.assertTrue(self.bot._execute_actual())  # distance-backoff: +BBE instead of polling every block

    def test_A2_deposit_sent(self):
        self._set_alloc(seed=[100, 0], topup=[0, 0])
        self.bot._deposit_to_module = Mock(return_value=True)
        self.assertTrue(self.bot._execute_actual())  # +BBE
        self.bot._deposit_to_module.assert_called_once_with(5)

    def test_A3_deposit_failed(self):
        self._set_alloc(seed=[100, 0], topup=[0, 0])
        self.bot._deposit_to_module = Mock(return_value=False)
        self.assertFalse(self.bot._execute_actual())  # +1
        self.bot._deposit_to_module.assert_called_once_with(5)

    def test_A4_quorum_retained_wait(self):
        self._set_alloc(seed=[100, 0], topup=[0, 0])
        self.bot._get_quorum = Mock(return_value=None)  # no quorum now, heartbeat fresh → retained
        self.bot._deposit_to_module = Mock(return_value=True)
        self.assertFalse(self.bot._execute_actual())  # +1
        self.bot._deposit_to_module.assert_not_called()

    def test_A5_quorum_stale_phase_a_skips(self):
        self._set_alloc(seed=[100, 0], topup=[0, 0])  # no top-up, no 0x01 → Phase B empty
        self.bot._get_quorum = Mock(return_value=None)
        self._stale_quorum(5)
        self.bot._deposit_to_module = Mock(return_value=True)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self.assertFalse(self.bot._execute_actual())  # +1
        self.bot._deposit_to_module.assert_not_called()
        self.bot._top_up_to_module.assert_not_called()

    def test_A6_quorum_retained_holds_priority_over_ready_module(self):
        self.bot._deposit_to_module = Mock()
        # Two 0x02 seed candidates. Priority m5 (lower stake) has no quorum but is in retention → we
        # WAIT and do NOT divert to m2, even though m2 has a quorum and could deposit right now.
        variables.DEPOSIT_MODULES_WHITELIST = [5, 2]
        self.bot._module_last_heart_beat = {5: datetime.now(), 2: datetime.now()}  # both retained (fresh)
        self.bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(
            return_value=[_make_digest(5, '0x5', 2), _make_digest(2, '0x2', 2)]
        )

        def alloc(_amount, is_top_up):
            if is_top_up:
                return (0, [0, 0], [0, 0])
            return (0, [100, 100], [200, 2000])  # m5 stake=100 (priority), m2 stake=1900

        self.bot.w3.lido.staking_router.get_deposit_allocations = Mock(side_effect=alloc)
        self.bot._get_quorum = Mock(side_effect=lambda module_id: ['msg'] if module_id == 2 else None)  # only m2 has quorum

        self.assertFalse(self.bot._execute_actual())  # WAIT on priority m5 (+1)
        self.bot._deposit_to_module.assert_not_called()  # did NOT divert to the ready m2

    # ─── B. top-up candidate (Phase B 0x02) ────────────────────

    def test_B3_top_up_distance_not_passed(self):
        self._set_alloc(seed=[0, 0], topup=[100, 0])
        self.bot.w3.lido.topup_gateway.is_block_distance_passed = Mock(return_value=False)
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self.assertTrue(self.bot._execute_actual())  # distance-backoff: +BBE instead of polling every block
        self.bot._top_up_to_module.assert_not_called()

    def test_B4_top_up_sent(self):
        self._set_alloc(seed=[0, 0], topup=[100, 0])
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.SENT)
        self.assertTrue(self.bot._execute_actual())  # +BBE
        self.bot._top_up_to_module.assert_called_once()

    def test_B5_top_up_failed(self):
        self._set_alloc(seed=[0, 0], topup=[100, 0])
        self.bot._top_up_to_module = Mock(return_value=PhaseOutcome.TX_FAILED)
        self.assertFalse(self.bot._execute_actual())  # +1
        self.bot._top_up_to_module.assert_called_once()


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
    """_select_strategy returns CSM strategy when staking_module.get_type() returns MODULE_TYPE_CSM."""
    mock_module = Mock()
    mock_module.get_type.return_value = MODULE_TYPE_CSM
    depositor_bot.w3.lido.staking_module = Mock(return_value=mock_module)
    depositor_bot._csm_strategy.is_gas_price_ok = Mock(return_value=False)
    depositor_bot._general_strategy.is_gas_price_ok = Mock(return_value=False)

    depositor_bot._deposit_to_module(4)

    depositor_bot._csm_strategy.is_gas_price_ok.assert_called_once_with(4)
    depositor_bot._general_strategy.is_gas_price_ok.assert_not_called()


@pytest.mark.unit
def test_deposit_to_module_general_strategy_for_non_csm_module_type(depositor_bot):
    """_select_strategy returns general strategy when staking_module.get_type() returns a non-CSM type."""
    mock_module = Mock()
    mock_module.get_type.return_value = b'curated-onchain-v1'.ljust(32, b'\x00')
    depositor_bot.w3.lido.staking_module = Mock(return_value=mock_module)
    depositor_bot._csm_strategy.is_gas_price_ok = Mock(return_value=False)
    depositor_bot._general_strategy.is_gas_price_ok = Mock(return_value=False)

    depositor_bot._deposit_to_module(1)

    depositor_bot._general_strategy.is_gas_price_ok.assert_called_once_with(1)
    depositor_bot._csm_strategy.is_gas_price_ok.assert_not_called()


# ─── _top_up_to_module ─────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.unit
def test_top_up_to_module_unknown_type_returns_false(depositor_bot):
    mock_module = Mock()
    mock_module.get_type.return_value = b'unknown-type'.ljust(32, b'\x00')
    depositor_bot.w3.lido.staking_module = Mock(return_value=mock_module)
    depositor_bot._select_topup_strategy = Mock(return_value=None)

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is PhaseOutcome.SKIPPED


@pytest.mark.unit
def test_top_up_to_module_gas_too_high_returns_false(depositor_bot):
    mock_module = Mock()
    mock_module.get_type.return_value = MODULE_TYPE_CMV2
    depositor_bot.w3.lido.staking_module = Mock(return_value=mock_module)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=False)
    strategy.get_topup_candidates = Mock()
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is PhaseOutcome.SKIPPED
    strategy.get_topup_candidates.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_no_proof_data_returns_false(depositor_bot):
    mock_module = Mock()
    mock_module.get_type.return_value = MODULE_TYPE_CMV2
    depositor_bot.w3.lido.staking_module = Mock(return_value=mock_module)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.get_topup_candidates = Mock(return_value=None)
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)
    depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=10)
    depositor_bot.w3.lido.topup_gateway.top_up = Mock()

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is PhaseOutcome.SKIPPED
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
        mock_module = Mock()
        mock_module.get_type.return_value = MODULE_TYPE_CMV2
        depositor_bot.w3.lido.staking_module = Mock(return_value=mock_module)
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

    mock_module = Mock()
    mock_module.get_type.return_value = MODULE_TYPE_CMV2
    depositor_bot.w3.lido.staking_module = Mock(return_value=mock_module)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.get_topup_candidates = Mock(return_value=proof_data)
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)
    depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=10)
    top_up = Mock(return_value=tx)
    depositor_bot.w3.lido.topup_gateway.top_up = top_up
    check = Mock(return_value=True)
    depositor_bot.w3.transaction.check = check
    depositor_bot.w3.transaction.send = Mock(return_value=True)

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is PhaseOutcome.SENT

    top_up.assert_called_once_with(1, proof_data)
    check.assert_called_once_with(tx)
    depositor_bot.w3.transaction.send.assert_called_once_with(tx, False, 6)


@pytest.mark.unit
def test_top_up_to_module_passes_module_allocation_through_to_strategy(depositor_bot):
    """The allocation is forwarded to get_topup_candidates, not re-queried."""
    mock_module = Mock()
    mock_module.get_type.return_value = MODULE_TYPE_CMV2
    depositor_bot.w3.lido.staking_module = Mock(return_value=mock_module)
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


# ─── _build_consolidation_indexer ──────────────────────────────────


@pytest.mark.unit
def test_build_consolidation_indexer_none_when_top_up_disabled():
    variables.ENABLE_TOP_UP = False
    bot = _make_bot()
    assert bot._build_consolidation_indexer() is None


@pytest.mark.unit
def test_build_consolidation_indexer_raises_when_top_up_enabled_but_bus_unconfigured():
    # ENABLE_TOP_UP on + no Bus config → fail fast at startup (don't run with top-ups silently off).
    variables.ENABLE_TOP_UP = True
    bot = _make_bot()
    with mock.patch.object(variables, 'get_consolidation_bus_config', return_value=(None, None)), pytest.raises(ValueError):
        bot._build_consolidation_indexer()


# ─── top-up execution path (direct vs delegated) ───────────────────


def _delegation_mock(bot, *, delegate, terminated=False, delegation_has_role=True, account_has_role=True):
    """Attach a delegation contract mock plus a role table for (delegation, bot account)."""
    delegation = Mock()
    delegation.address = '0xDe1e9a710000000000000000000000000000BEEF'
    delegation.is_terminated = Mock(return_value=terminated)
    delegation.get_delegate = Mock(return_value=delegate)
    delegation.wrap = Mock(side_effect=lambda call: ('wrapped', call))
    bot.w3.lido.delegation = delegation
    _role_table(bot, {delegation.address: delegation_has_role}, account_has_role)
    return delegation


def _role_table(bot, holders: dict, account_has_role=True):
    """Stub TOP_UP_ROLE lookups: holders maps address → hasRole, bot account handled separately."""
    role = b'\x01' * 32
    bot.w3.lido.topup_gateway.top_up_role = Mock(return_value=role)

    def has_role(_role, address):
        if variables.ACCOUNT is not None and address == variables.ACCOUNT.address:
            return account_has_role
        return holders.get(address, False)

    bot.w3.lido.topup_gateway.has_role = Mock(side_effect=has_role)


@pytest.fixture
def account(monkeypatch):
    acc = Mock()
    acc.address = '0xB07B07B07B07B07B07B07B07B07B07B07B07B07B'
    monkeypatch.setattr(variables, 'ACCOUNT', acc)
    return acc


@pytest.mark.unit
def test_path_direct_when_no_delegation_configured(depositor_bot, account):
    _role_table(depositor_bot, {}, account_has_role=True)
    assert depositor_bot._resolve_topup_path() is TopUpPath.DIRECT


@pytest.mark.unit
def test_path_no_role_when_nobody_holds_the_role(depositor_bot, account):
    """Pre-existing misconfiguration that used to be invisible: role never granted to the key."""
    _role_table(depositor_bot, {}, account_has_role=False)
    assert depositor_bot._resolve_topup_path() is TopUpPath.NO_ROLE


@pytest.mark.unit
def test_path_delegated_when_delegation_holds_role_and_bot_is_delegate(depositor_bot, account):
    _delegation_mock(depositor_bot, delegate=account.address)
    assert depositor_bot._resolve_topup_path() is TopUpPath.DELEGATED


@pytest.mark.unit
def test_path_prefers_delegation_over_direct_when_both_hold_the_role(depositor_bot, account):
    """The overlap state mid-migration: both identities hold the role. Delegation wins, so the
    cutover is complete as soon as the grant lands — revoking from the key changes nothing."""
    _delegation_mock(depositor_bot, delegate=account.address, account_has_role=True)
    assert depositor_bot._resolve_topup_path() is TopUpPath.DELEGATED


@pytest.mark.unit
def test_path_direct_when_delegation_has_no_role_yet(depositor_bot, account):
    """Before the grant lands: delegation is configured but the key still carries the role."""
    _delegation_mock(depositor_bot, delegate=account.address, delegation_has_role=False)
    assert depositor_bot._resolve_topup_path() is TopUpPath.DIRECT


@pytest.mark.unit
@pytest.mark.parametrize(
    'kwargs,expected',
    [
        ({'delegate': '0x0000000000000000000000000000000000000001'}, TopUpPath.NOT_DELEGATE),
        ({'delegate': None, 'terminated': True}, TopUpPath.TERMINATED),
    ],
)
def test_path_reports_delegation_fault_when_direct_is_not_available(depositor_bot, account, kwargs, expected):
    kwargs['delegate'] = kwargs['delegate'] or account.address
    _delegation_mock(depositor_bot, account_has_role=False, **kwargs)
    assert depositor_bot._resolve_topup_path() is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    'kwargs',
    [
        {'delegate': '0x0000000000000000000000000000000000000001'},  # delegate rotated away
        {'delegate': None, 'terminated': True},
    ],
)
def test_path_falls_back_to_direct_when_delegation_is_broken(depositor_bot, account, kwargs):
    """A revoked delegate or a terminated contract must not strand the bot while its own key still
    holds the role — this is what removes the need for a restart timed to the role transactions."""
    kwargs['delegate'] = kwargs['delegate'] or account.address
    _delegation_mock(depositor_bot, account_has_role=True, **kwargs)
    assert depositor_bot._resolve_topup_path() is TopUpPath.DIRECT


@pytest.mark.unit
def test_path_direct_in_dry_mode_without_account(depositor_bot, monkeypatch):
    """No key to compare against and nothing gets sent — don't block on identity checks."""
    monkeypatch.setattr(variables, 'ACCOUNT', None)
    _role_table(depositor_bot, {}, account_has_role=False)
    assert depositor_bot._resolve_topup_path() is TopUpPath.DIRECT


@pytest.mark.unit
def test_validate_refuses_to_start_when_delegation_configured_but_no_path_works(depositor_bot, account):
    _delegation_mock(depositor_bot, delegate='0x0000000000000000000000000000000000000001', account_has_role=False)
    with (
        mock.patch.object(variables, 'ENABLE_TOP_UP', True),
        mock.patch.object(variables, 'DELEGATION_CONTRACT_ADDRESS', '0xDe1e9a710000000000000000000000000000BEEF'),
        pytest.raises(ValueError, match='No usable path'),
    ):
        depositor_bot._validate_topup_delegation()


@pytest.mark.unit
def test_validate_only_warns_when_no_role_and_no_delegation_configured(depositor_bot, account):
    """Pre-existing deployments must not turn an upgrade into a boot failure."""
    _role_table(depositor_bot, {}, account_has_role=False)
    with (
        mock.patch.object(variables, 'ENABLE_TOP_UP', True),
        mock.patch.object(variables, 'DELEGATION_CONTRACT_ADDRESS', None),
    ):
        depositor_bot._validate_topup_delegation()  # does not raise
    assert depositor_bot._topup_path is TopUpPath.NO_ROLE


@pytest.mark.unit
def test_validate_passes_and_records_path_when_executable(depositor_bot, account):
    _delegation_mock(depositor_bot, delegate=account.address)
    with mock.patch.object(variables, 'ENABLE_TOP_UP', True):
        depositor_bot._validate_topup_delegation()
    assert depositor_bot._topup_path is TopUpPath.DELEGATED


@pytest.mark.unit
def test_validate_skipped_when_top_up_disabled(depositor_bot, account):
    """A broken delegation is irrelevant while top-up is off — don't block the deposit-only bot."""
    delegation = _delegation_mock(depositor_bot, delegate=account.address, terminated=True)
    with mock.patch.object(variables, 'ENABLE_TOP_UP', False):
        depositor_bot._validate_topup_delegation()
    delegation.is_terminated.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_sends_direct_call_on_the_direct_path(depositor_bot):
    tx = Mock(name='tx')
    _stub_topup_happy_path(depositor_bot, tx)
    depositor_bot._topup_path = TopUpPath.DIRECT

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is PhaseOutcome.SENT
    depositor_bot.w3.transaction.check.assert_called_once_with(tx)
    depositor_bot.w3.transaction.send.assert_called_once_with(tx, False, 6)


@pytest.mark.unit
def test_top_up_to_module_wraps_call_before_dry_run_on_the_delegated_path(depositor_bot, account):
    """The wrapped tx — not the bare topUp — must reach check() and send(): the direct call would
    revert with AccessControlUnauthorizedAccount, since the role is held by the delegation contract."""
    tx = Mock(name='tx')
    _stub_topup_happy_path(depositor_bot, tx)
    delegation = _delegation_mock(depositor_bot, delegate=account.address)
    depositor_bot._topup_path = TopUpPath.DELEGATED

    assert depositor_bot._top_up_to_module(1, '0xAddr', 50) is PhaseOutcome.SENT

    delegation.wrap.assert_called_once_with(tx)
    depositor_bot.w3.transaction.check.assert_called_once_with(('wrapped', tx))
    depositor_bot.w3.transaction.send.assert_called_once_with(('wrapped', tx), False, 6)


def _stub_topup_happy_path(bot, tx):
    """Stub everything _top_up_to_module needs up to building the tx."""
    mock_module = Mock()
    mock_module.get_type.return_value = MODULE_TYPE_CMV2
    bot.w3.lido.staking_module = Mock(return_value=mock_module)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.get_topup_candidates = Mock(return_value=['proof'])
    bot._select_topup_strategy = Mock(return_value=strategy)
    bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=10)
    bot.w3.lido.topup_gateway.top_up = Mock(return_value=tx)
    bot.w3.transaction.check = Mock(return_value=True)
    bot.w3.transaction.send = Mock(return_value=True)


# ─── _select_topup_strategy ────────────────────────────────────────


@pytest.mark.unit
def test_select_topup_strategy_cmv2_returns_cmv2_strategy(depositor_bot):
    strategy = depositor_bot._select_topup_strategy(MODULE_TYPE_CMV2)
    assert strategy is depositor_bot._cmv2_topup_strategy


@pytest.mark.unit
def test_select_topup_strategy_unknown_returns_none(depositor_bot):
    unknown_type = b'something-else'.ljust(32, b'\x00')
    assert depositor_bot._select_topup_strategy(unknown_type) is None


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
    # {delegate_EOA: guardian_contract}: delegate 0x7099… is the active delegate of guardian 0x4346….
    depositor_bot.w3.lido.get_guardian_delegates = Mock(
        return_value={'0x70997970C51812dc3A010C7d01b50e0d17dc79C8': '0x43464Fe06c18848a2E2e913194D64c1970f4326a'}
    )


@pytest.mark.unit
def test_depositor_message_actualizer(setup_deposit_message, depositor_bot, deposit_message, block_data):
    message_filter = depositor_bot._get_message_actualize_filter()
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_not_guardian(setup_deposit_message, depositor_bot, deposit_message, block_data):
    # Legacy (no delegate on the message): guardian must still be registered — here it is not.
    depositor_bot.w3.lido.get_guardian_delegates = Mock(
        return_value={'0x70997970C51812dc3A010C7d01b50e0d17dc79C8': '0x13464Fe06c18848a2E2e913194D64c1970f4326a'}
    )
    message_filter = depositor_bot._get_message_actualize_filter()
    assert not list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_delegate_fresh(setup_deposit_message, depositor_bot, deposit_message, block_data):
    # Data Bus message carrying its delegate; the delegate still maps to the claimed guardian → kept.
    deposit_message['guardianDelegate'] = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8'
    message_filter = depositor_bot._get_message_actualize_filter()
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_delegate_rotated(setup_deposit_message, depositor_bot, deposit_message, block_data):
    # Signer delegate is no longer the guardian's active delegate (rotated/revoked/terminated) → dropped.
    deposit_message['guardianDelegate'] = '0x000000000000000000000000000000000000dEaD'
    message_filter = depositor_bot._get_message_actualize_filter()
    assert not list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_delegate_wrong_guardian(setup_deposit_message, depositor_bot, deposit_message, block_data):
    # Delegate is active but now bound to a different guardian than the message claims → dropped.
    deposit_message['guardianDelegate'] = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8'
    deposit_message['guardianAddress'] = '0x33464Fe06c18848a2E2e913194D64c1970f4326a'
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
def test_depositor_message_actualizer_far_future_block(setup_deposit_message, depositor_bot, deposit_message, block_data):
    """A blockNumber far ahead of head must be dropped, not retained as "cannot verify yet"."""
    message_filter = depositor_bot._get_message_actualize_filter()

    deposit_message['blockNumber'] = block_data['number'] + MESSAGE_BLOCK_WINDOW
    assert list(filter(message_filter, [deposit_message])), 'edge of the window is still relevant'

    deposit_message['blockNumber'] = block_data['number'] + MESSAGE_BLOCK_WINDOW + 1
    assert not list(filter(message_filter, [deposit_message]))

    deposit_message['blockNumber'] = block_data['number'] + 10**9
    assert not list(filter(message_filter, [deposit_message]))


# ─── Signature verification happens on ingestion, once per message ──


_ATTEST_PREFIX = b'\x11' * 32
_BLOCK_HASH = '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532'
_DEPOSIT_ROOT = '0x64dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b'


class _StubTransport:
    def __init__(self, messages):
        self._messages = messages

    def get_messages(self):
        return self._messages


def _signed_deposit_message(nonce: int = 12) -> dict:
    """Deposit message signed by COUNCIL_1 under the v4 (non-delegated) scheme."""
    digest = Web3.solidity_keccak(
        ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
        [_ATTEST_PREFIX, 10, _BLOCK_HASH, _DEPOSIT_ROOT, 1, nonce],
    )
    signed = Account.unsafe_sign_hash(digest, COUNCIL_PK_1)
    return {
        'type': 'deposit',
        'blockNumber': 10,
        'blockHash': _BLOCK_HASH,
        'depositRoot': _DEPOSIT_ROOT,
        'stakingModuleId': 1,
        'nonce': nonce,
        'guardianAddress': COUNCIL_ADDRESS_1,
        'signature': {
            'r': '0x' + signed.r.to_bytes(32, 'big').hex(),
            '_vs': compute_vs(signed.v, '0x' + signed.s.to_bytes(32, 'big').hex()),
        },
    }


@pytest.mark.unit
def test_bad_signature_dropped_on_ingestion():
    """The sign filter must be wired into the storage's static (per-message) filters."""
    bot = _make_bot(attest_prefix=_ATTEST_PREFIX)
    good = _signed_deposit_message()
    tampered = _signed_deposit_message()
    tampered['nonce'] += 1

    bot.message_storage.clear()
    bot.message_storage._transports = [_StubTransport([good, tampered])]
    try:
        kept = bot.message_storage.get_messages_and_actualize(lambda x: True)
        assert [m['nonce'] for m in kept] == [good['nonce']]
    finally:
        bot.message_storage.clear()


@pytest.mark.unit
def test_retained_messages_are_not_reverified_every_cycle():
    """Verification must not re-run over the retained list on every call."""
    bot = _make_bot()
    prefix_calls = bot.w3.lido.deposit_security_module.get_attest_message_prefix
    assert prefix_calls.call_count == 1, 'the attest prefix is a constant — read once at startup'

    bot.message_storage.clear()
    bot._get_message_actualize_filter = Mock(return_value=lambda x: True)
    try:
        for _ in range(5):
            bot._fetch_actual_messages()
    finally:
        bot.message_storage.clear()

    assert prefix_calls.call_count == 1


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


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration,module_id',
    [[{'block': 3247161}, 1]],  # hoodi block
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
    variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3, 4, 5]
    variables.ENABLE_TOP_UP = False
    # The staking-module cache is built at fixture init time from the whitelist; rebuild it now that the
    # test set its own whitelist, otherwise _refresh_modules_state raises KeyError on the new module ids.
    web3_lido_integration.lido._load_staking_modules()

    web3_lido_integration.provider.make_request(
        'anvil_setBalance',
        [
            web3_lido_integration.eth.accounts[0],
            '0x500000000000000000000000',
        ],
    )

    for _ in range(15):
        # submit() reverts with STAKE_LIMIT if value exceeds the current stake limit — cap each
        # submit to what the rate-limit bucket allows, then mine a block so it replenishes.
        stake_limit = web3_lido_integration.lido.lido.functions.getCurrentStakeLimit().call()
        value = min(10000 * 10**18, stake_limit)
        if value > 0:
            web3_lido_integration.lido.lido.functions.submit(web3_lido_integration.eth.accounts[0]).transact(
                {
                    'from': web3_lido_integration.eth.accounts[0],
                    'value': value,
                }
            )
        web3_lido_integration.provider.make_request('anvil_mine', [1])

    # At this fork block module 1 (the only one with depositable keys) has stakeShareLimit=0, so the
    # allocation algorithm returns 0 for every module and nothing gets deposited. Raise its share limit
    # (impersonating the STAKING_MODULE_MANAGE_ROLE holder) so it receives a non-zero allocation.
    # TODO: temporary — remove once there is a helper to add keys to the other (new) modules, so we can
    # get a non-zero allocation without touching share limits.
    sr = web3_lido_integration.lido.staking_router
    manage_role = sr.functions.STAKING_MODULE_MANAGE_ROLE().call()
    sr_admin = sr.functions.getRoleMember(manage_role, 0).call()
    web3_lido_integration.provider.make_request('anvil_impersonateAccount', [sr_admin])
    web3_lido_integration.provider.make_request('anvil_setBalance', [sr_admin, '0x500000000000000000000000'])
    m1 = sr.functions.getStakingModule(module_id).call()
    sr.functions.updateStakingModule(
        module_id,
        10000,  # stakeShareLimit → 100%
        m1.priorityExitShareThreshold or 10000,
        m1.stakingModuleFee,
        m1.treasuryFee,
        m1.maxDepositsPerBlock,
        m1.minDepositBlockDistance,
    ).transact({'from': sr_admin})

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
