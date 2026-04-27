import unittest
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import MagicMock, Mock, patch

import pytest
import variables
from bots.depositor import DepositorBot

from tests.conftest import COUNCIL_ADDRESS_1, COUNCIL_ADDRESS_2, COUNCIL_PK_1, COUNCIL_PK_2
from tests.utils.protocol_utils import get_deposit_message


@pytest.mark.unit
class TestGetPreferredToDepositModules(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_w3 = MagicMock()
        self.mock_sender = MagicMock()
        self.mock_general_strategy = MagicMock()
        self.mock_csm_strategy = MagicMock()

        # Initialize the bot
        self.bot = DepositorBot(
            w3=self.mock_w3,
            sender=self.mock_sender,
            base_deposit_strategy=self.mock_general_strategy,
            csm_strategy=self.mock_csm_strategy,
            gas_price_calculator=MagicMock(),
            keys_api=MagicMock(),
            cl=MagicMock(),
        )

        # Set up initial state
        self.now = datetime.now()
        self.bot._module_last_heart_beat = {
            1: self.now - timedelta(minutes=2),  # Healthy
            2: self.now - timedelta(minutes=10),  # Unhealthy
            3: self.now - timedelta(minutes=4),  # Healthy
        }

        # Mock whitelist
        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]

    @patch('datetime.datetime')
    def test_get_preferred_to_deposit_modules(self, mock_datetime):
        mock_datetime.now.return_value = self.now

        # Mock staking router module IDs and digests
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = [1, 2, 3]
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = [
            [0, 0, [1], [5, 8]],  # Module 1: 3 active validators
            [0, 0, [2], [7, 8]],  # Module 2: 1 active validator
            [0, 0, [3], [10, 16]],  # Module 3: 6 active validators
        ]
        self.bot._get_quorum = Mock()
        self.bot._select_strategy = Mock()

        # Mock module healthiness and quorum
        # Module ID:                                                            2      1      3
        self.bot._is_module_healthy_keys_amount_check = MagicMock(side_effect=[True, False, True])

        # Call the method
        result = self.bot._get_preferred_to_deposit_modules()

        # Expected output: Module 2 (1 active)
        self.assertEqual([2], result)

        # Verify calls to dependent methods
        self.bot._get_quorum.assert_any_call(1)
        self.bot._get_quorum.assert_any_call(2)
        self.bot._get_quorum.assert_any_call(3)
        self.bot._is_module_healthy_keys_amount_check.assert_any_call(1)
        self.bot._is_module_healthy_keys_amount_check.assert_any_call(2)
        self.bot._is_module_healthy_keys_amount_check.assert_any_call(3)

    def test_empty_whitelist(self):
        # Empty whitelist
        variables.DEPOSIT_MODULES_WHITELIST = []

        # Mock module IDs and digests
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = []
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = []

        # Call the method
        result = self.bot._get_preferred_to_deposit_modules()

        # Expected output: No modules available
        self.assertEqual([], result)

    def test_no_healthy_modules(self):
        # Mock staking router module IDs and digests
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = [1, 2]
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = [
            [0, 0, [1], [3, 5]],  # Module 1: 2 validators
            [0, 0, [2], [7, 9]],  # Module 2: 2 validators
        ]
        self.bot._get_quorum = Mock()

        # Mock module healthiness and quorum
        self.bot._is_module_healthy_keys_amount_check = MagicMock(side_effect=[False, False])

        # Call the method
        result = self.bot._get_preferred_to_deposit_modules()

        self.assertEqual([], result)

    def test_module_sorting_by_validator_difference(self):
        # Mock staking router module IDs and digests
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = [1, 2, 3]
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = [
            [0, 0, [1], [6, 10]],  # Module 1: 4 validators
            [0, 0, [2], [8, 13]],  # Module 2: 5 validators
            [0, 0, [3], [7, 8]],  # Module 3: 1 validator
        ]

        # Mock module healthiness and quorum
        self.bot._get_quorum = MagicMock(side_effect=[True, True, True])
        self.bot._is_module_healthy_keys_amount_check = MagicMock(side_effect=[True, True, True])

        # Call the method
        result = self.bot._get_preferred_to_deposit_modules()

        # Expected output: Sorted by validator difference: Module 3, Module 1, Module 2
        self.assertEqual([3], result)


@pytest.mark.unit
class TestGetPreferredToSeedDepositsModules(unittest.TestCase):
    """
    Tests for _get_preferred_to_seed_deposits_modules (Phase 1 selector).
    Phase 1 picks 0x02 modules with reserved seed buffer.
    """

    def setUp(self):
        self.mock_w3 = MagicMock()
        self.mock_sender = MagicMock()
        self.mock_general_strategy = MagicMock()
        self.mock_csm_strategy = MagicMock()
        self.mock_keys_api = MagicMock()
        self.mock_cl = MagicMock()

        self.bot = DepositorBot(
            w3=self.mock_w3,
            sender=self.mock_sender,
            base_deposit_strategy=self.mock_general_strategy,
            csm_strategy=self.mock_csm_strategy,
            gas_price_calculator=MagicMock(),
            keys_api=self.mock_keys_api,
            cl=self.mock_cl,
        )

        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]

        # heartbeat fresh by default (initialized in __init__ to now())
        self.mock_w3.lido.deposit_security_module.can_deposit.return_value = True
        # heartbeats stay fresh from __init__ when _get_quorum returns falsy
        self.bot._get_quorum = Mock(return_value=None)
        self.mock_w3.lido.lido.get_depositable_ether.return_value = 100 * 10**18

    @staticmethod
    def _digest(module_id, address, wc_type):
        # digest[2] = StakingModule tuple: (id, address, ..., wc_type@13, ...)
        return (
            10,
            5,
            (module_id, address, 500, 500, 1000, 0, f'module{module_id}', 0, 0, 0, 0, 150, 25, wc_type, 0, 0),
            (0, 100, 10),
        )

    def _set_no_recent_quorum(self, module_id):
        """Mark the module as having no quorum within QUORUM_RETENTION_MINUTES."""
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    # ─── Early exits ────────────────────────────────────────────────

    def test_no_depositable_ether(self):
        self.mock_w3.lido.lido.get_depositable_ether.return_value = 0
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
        ]

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([], result)
        # allocations not requested when no depositable ether
        self.mock_w3.lido.staking_router.get_deposit_allocations.assert_not_called()

    def test_no_seed_allocation_total_zero(self):
        # total == 0 means buffer is not reserved for seed → fall through to phase 2
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (0, [0], [0])

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([], result)

    # ─── Filters ────────────────────────────────────────────────────

    def test_non_0x02_modules_filtered(self):
        # 0x01 module with alloc>0 in whitelist — Phase 1 must skip it (only 0x02 eligible)
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 1),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (50, [50], [100])

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([], result)

    def test_zero_allocation_modules_filtered(self):
        # module1: 0x02, in whitelist, allocated[0]=0 → skipped
        # module2: 0x02, in whitelist, allocated[1]>0 → candidate
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (50, [0, 50], [0, 100])

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([2], result)

    def test_module_not_in_whitelist_filtered(self):
        # Module 4 is 0x02 with alloc>0 but not in WHITELIST = [1, 2, 3]
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(4, '0xAddr4', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (50, [50], [100])

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([], result)

    # ─── Sort & selection ───────────────────────────────────────────

    def test_sort_by_current_stake_asc(self):
        # current_stake = new_allocations - allocated
        #   module1: 110 - 10 = 100
        #   module2:  70 - 50 =  20  ← lowest first
        #   module3:  80 - 30 =  50
        # All healthy → return only the lowest-stake one
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
            self._digest(3, '0xAddr3', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (90, [10, 50, 30], [110, 70, 80])

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([2], result)

    def test_lowest_stake_healthy_returns_single(self):
        # heartbeat fresh from __init__, can_deposit=True from setUp
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (50, [50], [100])

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([1], result)

    def test_lowest_stake_unhealthy_fallback_to_next_healthy(self):
        # current_stake: module1=20 (lowest, no recent quorum), module2=50 (healthy)
        # Unhealthy anchor is included before the first healthy module.
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (80, [30, 50], [50, 100])
        self._set_no_recent_quorum(1)

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([1, 2], result)

    def test_all_unhealthy_returns_empty(self):
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (80, [30, 50], [50, 100])
        self._set_no_recent_quorum(1)
        self._set_no_recent_quorum(2)

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([], result)

    # ─── Side effects / regressions ─────────────────────────────────

    def test_heartbeat_refreshed_on_truthy_quorum(self):
        # Module 1 in whitelist with stale heartbeat — _get_quorum truthy → refresh.
        # Module 4 NOT in whitelist — _get_quorum must NOT be called for it.
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(4, '0xAddr4', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (50, [50, 0], [100, 0])
        self._set_no_recent_quorum(1)
        self.bot._get_quorum = Mock(return_value=['msg'])

        before = self.bot._module_last_heart_beat[1]
        result = self.bot._get_preferred_to_seed_deposits_modules()
        after = self.bot._module_last_heart_beat[1]

        # heartbeat refreshed for whitelisted module with quorum
        self.assertGreater(after, before)
        # _get_quorum called only for whitelisted module 1, never for module 4
        self.bot._get_quorum.assert_called_once_with(1)
        # refreshed → healthy → returned as anchor
        self.assertEqual([1], result)

    def test_index_alignment_with_subset_whitelist(self):
        # SR has 4 0x02 modules, WHITELIST = [1, 3]. Without proper index alignment
        # against allocated[]/new_allocations[] (indexed by full SR list),
        # module 3 would accidentally pick up module 2's allocation.
        variables.DEPOSIT_MODULES_WHITELIST = [1, 3]
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),  # not whitelisted
            self._digest(3, '0xAddr3', 2),
            self._digest(4, '0xAddr4', 2),  # not whitelisted
        ]
        # current_stake for whitelisted: module1 = 70-50 = 20 (lowest); module3 = 80-30 = 50
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (2078, [50, 999, 30, 999], [70, 999, 80, 999])

        result = self.bot._get_preferred_to_seed_deposits_modules()

        self.assertEqual([1], result)


@pytest.mark.unit
class TestGetPreferredToFullDepositsOrTopupModules(unittest.TestCase):
    """
    Tests for _get_preferred_to_full_deposits_or_topup_modules (Phase 2 selector).
    """

    def setUp(self):
        self.mock_w3 = MagicMock()
        self.mock_sender = MagicMock()
        self.mock_general_strategy = MagicMock()
        self.mock_csm_strategy = MagicMock()
        self.mock_keys_api = MagicMock()
        self.mock_cl = MagicMock()

        self.bot = DepositorBot(
            w3=self.mock_w3,
            sender=self.mock_sender,
            base_deposit_strategy=self.mock_general_strategy,
            csm_strategy=self.mock_csm_strategy,
            gas_price_calculator=MagicMock(),
            keys_api=self.mock_keys_api,
            cl=self.mock_cl,
        )

        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        variables.ENABLE_TOP_UP = True

        # heartbeat fresh by default (initialized in __init__ to now())
        # _is_module_healthy needs canDeposit too — default True
        self.mock_w3.lido.deposit_security_module.can_deposit.return_value = True
        # heartbeat refresh inside the method calls _get_quorum — keep it None so
        # heartbeats remain at the "fresh" value set by __init__
        self.bot._get_quorum = Mock(return_value=None)
        self.mock_w3.lido.lido.get_depositable_ether.return_value = 100 * 10**18

    @staticmethod
    def _digest(module_id, address, wc_type):
        # digest[2] = StakingModule tuple: (id, address, ..., wc_type@13, ...)
        return (
            10,
            5,
            (module_id, address, 500, 500, 1000, 0, f'module{module_id}', 0, 0, 0, 0, 150, 25, wc_type, 0, 0),
            (0, 100, 10),
        )

    def _set_no_recent_quorum(self, module_id):
        """Mark the module as having no quorum within QUORUM_RETENTION_MINUTES."""
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    # ─── Early exits ────────────────────────────────────────────────

    def test_no_depositable_ether(self):
        self.mock_w3.lido.lido.get_depositable_ether.return_value = 0
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
        ]

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([], result)

    def test_no_allocation_total_zero(self):
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (0, [0], [0])

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([], result)

    def test_module_not_in_whitelist_filtered(self):
        # Module 4 has alloc>0 but is not in WHITELIST = [1, 2, 3]
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(4, '0xAddr4', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (50, [50], [50])
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([], result)

    # ─── Sort & filter ──────────────────────────────────────────────

    def test_sort_by_current_stake_asc(self):
        # current_stake = new_allocations - allocated
        #   module1: 110 - 10 = 100
        #   module2:  70 - 50 =  20  ← lowest stake first
        #   module3:  80 - 30 =  50
        # All can_top_up=True → return only the lowest-stake module (module2)
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
            self._digest(3, '0xAddr3', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (90, [10, 50, 30], [110, 70, 80])
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([(2, 2, '0xAddr2', 50)], result)

    def test_enable_top_up_false_skips_0x02(self):
        variables.ENABLE_TOP_UP = False
        # Both have alloc>0; 0x02 must be filtered out, 0x01 must remain
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 1),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (80, [30, 50], [130, 70])

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([(2, 1, '0xAddr2', 50)], result)

    # ─── 0x02 readiness (live can_top_up) ───────────────────────────

    def test_0x02_lowest_stake_ready_returns_single(self):
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (50, [50], [100])
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([(1, 2, '0xAddr1', 50)], result)

    def test_0x02_lowest_stake_not_ready_skip_to_next(self):
        # current_stake: module1=20 (lowest), module2=50
        # can_top_up: module1=False (skip), module2=True
        # Lowest-stake module1 must NOT appear in result
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (80, [30, 50], [50, 100])
        self.mock_w3.lido.topup_gateway.can_top_up.side_effect = [False, True]

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([(2, 2, '0xAddr2', 50)], result)

    def test_all_0x02_no_can_top_up(self):
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (80, [30, 50], [130, 70])
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = False

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([], result)

    # ─── 0x01 cooldown (heartbeat) ──────────────────────────────────

    def test_0x01_lowest_stake_healthy_returns_single(self):
        # heartbeat fresh from __init__, can_deposit=True from setUp
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 1),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (50, [50], [100])

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([(1, 1, '0xAddr1', 50)], result)

    def test_0x01_lowest_stake_no_recent_quorum_fallback_to_healthy_0x01(self):
        # current_stake: module1=20 (lowest, no recent quorum), module2=50 (healthy)
        # Unhealthy 0x01 is added as fallback before the healthy anchor
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 1),
            self._digest(2, '0xAddr2', 1),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (80, [30, 50], [50, 100])
        self._set_no_recent_quorum(1)

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual(
            [(1, 1, '0xAddr1', 30), (2, 1, '0xAddr2', 50)],
            result,
        )

    def test_0x01_lowest_stake_no_recent_quorum_fallback_to_ready_0x02(self):
        # Mixed: lowest-stake 0x01 has no recent quorum, next is ready 0x02
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 1),
            self._digest(2, '0xAddr2', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (80, [30, 50], [50, 100])
        self._set_no_recent_quorum(1)
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual(
            [(1, 1, '0xAddr1', 30), (2, 2, '0xAddr2', 50)],
            result,
        )

    def test_all_unhealthy_returns_empty(self):
        # 0x01 without recent quorum + 0x02 without can_top_up → no anchor
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 1),
            self._digest(2, '0xAddr2', 2),
        ]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (80, [30, 50], [50, 100])
        self._set_no_recent_quorum(1)
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = False

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([], result)

    # ─── Index alignment regression ─────────────────────────────────

    def test_index_alignment_with_subset_whitelist(self):
        # SR has 4 modules, WHITELIST = [1, 3]. Without proper index alignment
        # against allocated[]/new_allocations[] (indexed by full SR list),
        # module 3 would accidentally pick up module 2's allocation.
        variables.DEPOSIT_MODULES_WHITELIST = [1, 3]
        self.mock_w3.lido.staking_router.get_all_staking_module_digests.return_value = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),  # not whitelisted
            self._digest(3, '0xAddr3', 2),
            self._digest(4, '0xAddr4', 2),  # not whitelisted
        ]
        # current_stake for whitelisted: module1 = 70-50 = 20; module3 = 80-30 = 50
        # lowest stake = module1 → can_top_up=True → return [(1, 2, '0xAddr1', 50)]
        self.mock_w3.lido.staking_router.get_deposit_allocations.return_value = (2078, [50, 999, 30, 999], [70, 999, 80, 999])
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True

        result = self.bot._get_preferred_to_full_deposits_or_topup_modules()

        self.assertEqual([(1, 2, '0xAddr1', 50)], result)


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
        web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1, 2])
        web3_lido_unit.lido.staking_router.get_contract_version = Mock(return_value=3)
        web3_lido_unit.eth.get_block = Mock(return_value=block_data)
        yield DepositorBot(
            web3_lido_unit, deposit_transaction_sender, base_deposit_strategy, csm_strategy, gas_price_calculator, Mock(), Mock()
        )


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


@pytest.mark.unit
def test_depositor_one_module_deposited(depositor_bot, block_data):
    modules = list(range(10))
    depositor_bot._get_quorum = Mock(return_value=True)

    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=10 * 32 * 10**18)
    depositor_bot.w3.lido.staking_router.get_staking_module_ids = Mock(return_value=modules)
    depositor_bot.w3.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=0)
    depositor_bot.w3.lido.deposit_security_module.get_max_deposits = Mock(return_value=10)
    depositor_bot.w3.lido.staking_router.get_staking_module_digests = Mock(
        return_value=[
            (0, 0, (1,), (10, 20, 10)),
            (0, 0, (2,), (0, 10, 10)),
        ]
    )
    depositor_bot._general_strategy.is_gas_price_ok = Mock(return_value=True)
    depositor_bot._general_strategy.deposited_keys_amount = Mock(return_value=10)
    depositor_bot._check_balance = Mock()
    depositor_bot._deposit_to_module = Mock(return_value=True)
    assert depositor_bot.execute(block_data)

    assert depositor_bot._deposit_to_module.call_count == 1


@pytest.mark.unit
def test_depositor_legacy_no_modules_to_deposit(depositor_bot, block_data):
    # depositor_bot fixture pins SR version to 3 → _execute_legacy path,
    # which has no top-up fallback. Empty module list → execute returns False.
    depositor_bot._check_balance = Mock()
    depositor_bot._get_preferred_to_deposit_modules = Mock(return_value=[])
    assert depositor_bot.execute(block_data) is False


@pytest.mark.unit
def test_depositor_v4_phase1_success_skips_phase2(depositor_bot, block_data):
    depositor_bot._check_balance = Mock()
    depositor_bot.w3.lido.staking_router.get_contract_version = Mock(return_value=4)
    depositor_bot._execute_phase1 = Mock(return_value=True)
    depositor_bot._execute_phase2 = Mock()
    assert depositor_bot.execute(block_data) is True
    depositor_bot._execute_phase2.assert_not_called()


@pytest.mark.unit
def test_depositor_v4_phase1_fails_falls_back_to_phase2(depositor_bot, block_data):
    depositor_bot._check_balance = Mock()
    depositor_bot.w3.lido.staking_router.get_contract_version = Mock(return_value=4)
    depositor_bot._execute_phase1 = Mock(return_value=False)
    depositor_bot._execute_phase2 = Mock(return_value=True)
    assert depositor_bot.execute(block_data) is True
    depositor_bot._execute_phase2.assert_called_once_with()


@pytest.mark.unit
def test_depositor_v4_both_phases_fail_returns_false(depositor_bot, block_data):
    depositor_bot._check_balance = Mock()
    depositor_bot.w3.lido.staking_router.get_contract_version = Mock(return_value=4)
    depositor_bot._execute_phase1 = Mock(return_value=False)
    depositor_bot._execute_phase2 = Mock(return_value=False)
    assert depositor_bot.execute(block_data) is False


@pytest.mark.unit
def test_execute_phase1_empty_modules_returns_false(depositor_bot):
    depositor_bot._get_preferred_to_seed_deposits_modules = Mock(return_value=[])
    depositor_bot._deposit_to_module = Mock()

    assert depositor_bot._execute_phase1() is False
    depositor_bot._deposit_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_phase1_first_module_succeeds_short_circuits(depositor_bot):
    depositor_bot._get_preferred_to_seed_deposits_modules = Mock(return_value=[1, 2, 3])
    depositor_bot._deposit_to_module = Mock(return_value=True)

    assert depositor_bot._execute_phase1() is True
    depositor_bot._deposit_to_module.assert_called_once_with(1)


@pytest.mark.unit
def test_execute_phase1_all_modules_fail_returns_false(depositor_bot):
    depositor_bot._get_preferred_to_seed_deposits_modules = Mock(return_value=[1, 2, 3])
    depositor_bot._deposit_to_module = Mock(side_effect=[False, False, False])

    assert depositor_bot._execute_phase1() is False
    assert depositor_bot._deposit_to_module.call_count == 3
    assert [c.args for c in depositor_bot._deposit_to_module.call_args_list] == [(1,), (2,), (3,)]


@pytest.mark.unit
def test_execute_phase1_uses_deposit_to_module_not_top_up(depositor_bot):
    depositor_bot._get_preferred_to_seed_deposits_modules = Mock(return_value=[1])
    depositor_bot._deposit_to_module = Mock(return_value=True)
    depositor_bot._top_up_to_module = Mock()

    assert depositor_bot._execute_phase1() is True
    depositor_bot._deposit_to_module.assert_called_once_with(1)
    depositor_bot._top_up_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_phase2_empty_modules_returns_false(depositor_bot):
    depositor_bot._get_preferred_to_full_deposits_or_topup_modules = Mock(return_value=[])
    depositor_bot._deposit_to_module = Mock()
    depositor_bot._top_up_to_module = Mock()

    assert depositor_bot._execute_phase2() is False
    depositor_bot._deposit_to_module.assert_not_called()
    depositor_bot._top_up_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_phase2_routes_0x02_to_top_up(depositor_bot):
    module = (1, 2, '0xAddr1', 50)
    depositor_bot._get_preferred_to_full_deposits_or_topup_modules = Mock(return_value=[module])
    depositor_bot._top_up_to_module = Mock(return_value=True)
    depositor_bot._deposit_to_module = Mock()

    assert depositor_bot._execute_phase2() is True
    depositor_bot._top_up_to_module.assert_called_once_with(module)
    depositor_bot._deposit_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_phase2_routes_0x01_to_deposit(depositor_bot):
    module = (1, 1, '0xAddr1', 50)
    depositor_bot._get_preferred_to_full_deposits_or_topup_modules = Mock(return_value=[module])
    depositor_bot._deposit_to_module = Mock(return_value=True)
    depositor_bot._top_up_to_module = Mock()

    assert depositor_bot._execute_phase2() is True
    depositor_bot._deposit_to_module.assert_called_once_with(1)
    depositor_bot._top_up_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_phase2_mixed_0x01_fails_then_0x02_succeeds(depositor_bot):
    m1 = (1, 1, '0xAddr1', 30)
    m2 = (2, 2, '0xAddr2', 50)
    depositor_bot._get_preferred_to_full_deposits_or_topup_modules = Mock(return_value=[m1, m2])
    depositor_bot._deposit_to_module = Mock(return_value=False)
    depositor_bot._top_up_to_module = Mock(return_value=True)

    assert depositor_bot._execute_phase2() is True
    depositor_bot._deposit_to_module.assert_called_once_with(1)
    depositor_bot._top_up_to_module.assert_called_once_with(m2)


@pytest.mark.unit
def test_execute_phase2_all_modules_fail_returns_false(depositor_bot):
    m1 = (1, 1, '0xAddr1', 30)
    m2 = (2, 2, '0xAddr2', 50)
    depositor_bot._get_preferred_to_full_deposits_or_topup_modules = Mock(return_value=[m1, m2])
    depositor_bot._deposit_to_module = Mock(return_value=False)
    depositor_bot._top_up_to_module = Mock(return_value=False)

    assert depositor_bot._execute_phase2() is False
    assert depositor_bot._deposit_to_module.call_count == 1
    assert depositor_bot._top_up_to_module.call_count == 1


# ─── _select_topup_strategy / _get_module_type ─────────────────────


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


# ─── _is_module_healthy (no keys-amount check) ────────────────────


@pytest.mark.unit
def test_is_module_healthy_stale_heartbeat_returns_false(depositor_bot):
    depositor_bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)
    depositor_bot.w3.lido.deposit_security_module.can_deposit = Mock(return_value=True)

    assert depositor_bot._is_module_healthy(1) is False


@pytest.mark.unit
def test_is_module_healthy_can_deposit_false_returns_false(depositor_bot):
    depositor_bot._module_last_heart_beat[1] = datetime.now()
    depositor_bot.w3.lido.deposit_security_module.can_deposit = Mock(return_value=False)

    assert depositor_bot._is_module_healthy(1) is False


@pytest.mark.unit
def test_is_module_healthy_both_pass_returns_true(depositor_bot):
    depositor_bot._module_last_heart_beat[1] = datetime.now()
    depositor_bot.w3.lido.deposit_security_module.can_deposit = Mock(return_value=True)

    assert depositor_bot._is_module_healthy(1) is True


# ─── _is_module_healthy_keys_amount_check ──────────────────────────


@pytest.mark.unit
def test_keys_amount_check_module_unhealthy_returns_false(depositor_bot):
    depositor_bot._is_module_healthy = Mock(return_value=False)
    strategy = Mock()
    strategy.deposited_keys_amount = Mock(return_value=10)
    depositor_bot._select_strategy = Mock(return_value=strategy)

    assert depositor_bot._is_module_healthy_keys_amount_check(1) is False


@pytest.mark.unit
def test_keys_amount_check_zero_keys_returns_false(depositor_bot):
    depositor_bot._is_module_healthy = Mock(return_value=True)
    strategy = Mock()
    strategy.deposited_keys_amount = Mock(return_value=0)
    depositor_bot._select_strategy = Mock(return_value=strategy)

    assert depositor_bot._is_module_healthy_keys_amount_check(1) is False


@pytest.mark.unit
def test_keys_amount_check_both_pass_returns_true(depositor_bot):
    depositor_bot._is_module_healthy = Mock(return_value=True)
    strategy = Mock()
    strategy.deposited_keys_amount = Mock(return_value=5)
    depositor_bot._select_strategy = Mock(return_value=strategy)

    assert depositor_bot._is_module_healthy_keys_amount_check(1) is True


# ─── execute() SR-version routing ──────────────────────────────────


@pytest.mark.unit
def test_execute_sr_v3_routes_to_legacy(depositor_bot, block_data):
    depositor_bot._check_balance = Mock()
    depositor_bot.w3.lido.staking_router.get_contract_version = Mock(return_value=3)
    depositor_bot._execute_legacy = Mock(return_value=True)
    depositor_bot._execute_phase1 = Mock()
    depositor_bot._execute_phase2 = Mock()

    assert depositor_bot.execute(block_data) is True
    depositor_bot._execute_legacy.assert_called_once_with()
    depositor_bot._execute_phase1.assert_not_called()
    depositor_bot._execute_phase2.assert_not_called()


@pytest.mark.unit
def test_execute_sr_v4_routes_to_phases(depositor_bot, block_data):
    depositor_bot._check_balance = Mock()
    depositor_bot.w3.lido.staking_router.get_contract_version = Mock(return_value=4)
    depositor_bot._execute_legacy = Mock()
    depositor_bot._execute_phase1 = Mock(return_value=True)
    depositor_bot._execute_phase2 = Mock()

    assert depositor_bot.execute(block_data) is True
    depositor_bot._execute_phase1.assert_called_once_with()
    depositor_bot._execute_legacy.assert_not_called()


# ─── _top_up_to_module ─────────────────────────────────────────────


@pytest.mark.unit
def test_top_up_to_module_can_top_up_false_returns_false(depositor_bot):
    module = (1, 2, '0xAddr1', 50)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=False)
    depositor_bot._get_module_type = Mock()
    depositor_bot._select_topup_strategy = Mock()

    assert depositor_bot._top_up_to_module(module) is False
    depositor_bot._get_module_type.assert_not_called()
    depositor_bot._select_topup_strategy.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_unknown_module_type_returns_false(depositor_bot):
    module = (1, 2, '0xAddr1', 50)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    depositor_bot._get_module_type = Mock(return_value=b'unknown-type'.ljust(32, b'\x00'))
    depositor_bot._select_topup_strategy = Mock(return_value=None)

    assert depositor_bot._top_up_to_module(module) is False


@pytest.mark.unit
def test_top_up_to_module_gas_too_high_returns_false(depositor_bot):
    module = (1, 2, '0xAddr1', 50)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=False)
    strategy.get_topup_candidates = Mock()
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)

    assert depositor_bot._top_up_to_module(module) is False
    strategy.get_topup_candidates.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_no_candidates_returns_false(depositor_bot):
    module = (1, 2, '0xAddr1', 50)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=10)
    depositor_bot.w3.lido.topup_gateway.top_up = Mock()
    depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.get_topup_candidates = Mock(return_value=None)
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)

    assert depositor_bot._top_up_to_module(module) is False
    depositor_bot.w3.lido.topup_gateway.top_up.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_happy_path_returns_success(depositor_bot):
    module = (1, 2, '0xAddr1', 50)
    proof_data = ['proof']
    tx = Mock(name='tx')

    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=10)
    depositor_bot.w3.lido.topup_gateway.top_up = Mock(return_value=tx)
    depositor_bot.w3.transaction.check = Mock(return_value=True)
    depositor_bot.w3.transaction.send = Mock(return_value=True)
    depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.get_topup_candidates = Mock(return_value=proof_data)
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)

    assert depositor_bot._top_up_to_module(module) is True

    strategy.get_topup_candidates.assert_called_once_with(
        depositor_bot._keys_api,
        depositor_bot._cl,
        1,
        '0xAddr1',
        50,
        min(variables.MAX_VALIDATORS_PER_TOP_UP, 10),
    )
    depositor_bot.w3.lido.topup_gateway.top_up.assert_called_once_with(1, proof_data)
    depositor_bot.w3.transaction.check.assert_called_once_with(tx)
    depositor_bot.w3.transaction.send.assert_called_once_with(tx, False, 6)


@pytest.mark.unit
@pytest.mark.parametrize(
    'config_limit,gateway_limit,expected',
    [
        (50, 30, 30),  # gateway is smaller — contract limit wins
        (20, 100, 20),  # config is smaller — variable wins
    ],
)
def test_top_up_to_module_max_validators_uses_min(depositor_bot, config_limit, gateway_limit, expected):
    module = (1, 2, '0xAddr1', 50)

    original_config_limit = variables.MAX_VALIDATORS_PER_TOP_UP
    variables.MAX_VALIDATORS_PER_TOP_UP = config_limit
    try:
        depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
        depositor_bot.w3.lido.topup_gateway.get_max_validators_per_top_up = Mock(return_value=gateway_limit)
        depositor_bot.w3.lido.topup_gateway.top_up = Mock(return_value=Mock())
        depositor_bot.w3.transaction.check = Mock(return_value=True)
        depositor_bot.w3.transaction.send = Mock(return_value=True)
        depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
        strategy = Mock()
        strategy.is_gas_price_ok = Mock(return_value=True)
        strategy.get_topup_candidates = Mock(return_value=['proof'])
        depositor_bot._select_topup_strategy = Mock(return_value=strategy)

        depositor_bot._top_up_to_module(module)

        # max_validators is the 6th positional arg (index 5)
        assert strategy.get_topup_candidates.call_args.args[5] == expected
    finally:
        variables.MAX_VALIDATORS_PER_TOP_UP = original_config_limit


@pytest.mark.unit
@pytest.mark.parametrize(
    'is_depositable,quorum,is_gas_price_ok,is_deposited_keys_amount_ok',
    [
        pytest.param(True, True, True, True, marks=pytest.mark.xfail(raises=AssertionError, strict=True)),
        (False, True, True, True),
        (True, False, True, True),
        (True, True, False, True),
        (True, True, True, False),
    ],
)
def test_depositor_deposit_to_module(depositor_bot, is_depositable, quorum, is_gas_price_ok, is_deposited_keys_amount_ok):
    depositor_bot.w3.lido.deposit_security_module.can_deposit = Mock(return_value=is_depositable)
    depositor_bot._get_quorum = Mock(return_value=quorum)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=is_gas_price_ok)
    strategy.can_deposit_keys_based_on_ether = Mock(return_value=is_deposited_keys_amount_ok)
    depositor_bot._select_strategy = Mock(return_value=strategy)
    depositor_bot.prepare_and_send_tx = Mock()

    assert not depositor_bot._deposit_to_module(1)
    assert depositor_bot.prepare_and_send_tx.call_count == 0


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
    assert not list(
        filter(
            message_filter,
            [
                deposit_message,
            ],
        )
    )
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
    # Define the whitelist of deposit modules
    variables.DEPOSIT_MODULES_WHITELIST = [1, 2]
    variables.ENABLE_TOP_UP = False

    # Set the balance for the first account
    web3_lido_integration.provider.make_request(
        'anvil_setBalance',
        [
            web3_lido_integration.eth.accounts[0],
            '0x500000000000000000000000',
        ],
    )

    # Submit multiple transactions
    for _ in range(15):
        web3_lido_integration.lido.lido.functions.submit(web3_lido_integration.eth.accounts[0]).transact(
            {
                'from': web3_lido_integration.eth.accounts[0],
                'value': 10000 * 10**18,
            }
        )
    # Get the latest block
    latest = web3_lido_integration.eth.get_block('latest')

    # Get the current nonce for the staking module
    old_module_nonce = web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id)

    # Create deposit messages
    deposit_messages = [
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_1, COUNCIL_PK_1, module_id),
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_1, COUNCIL_PK_1, module_id),
        get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_2, COUNCIL_PK_2, module_id),
    ]

    # Mine a new block
    web3_lido_integration.provider.make_request('anvil_mine', [1])
    # this is done to ensure the deposit will be done to the target module
    web3_lido_integration.lido.staking_router.get_staking_module_ids = Mock(return_value=[module_id])

    # Initialize the DepositorBot
    db: DepositorBot = DepositorBot(
        web3_lido_integration,
        deposit_transaction_sender_integration,
        base_deposit_strategy_integration,
        csm_strategy_integration,
        gas_price_calculator_integration,
        Mock(),
        Mock(),
    )

    # Clear the message storage and execute the bot without any messages
    db.message_storage.messages = []
    db.execute(latest)

    # Assert that the staking module nonce has not changed
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce

    # Execute the bot with deposit messages and assert that the nonce has increased by 1
    db.message_storage.messages = deposit_messages
    assert db.execute(latest)
    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce + 1
