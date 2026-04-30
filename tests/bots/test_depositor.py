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
class TestBuildSeedList(unittest.TestCase):
    """
    Tests for _build_seed_list. Returns (candidates, has_healthy):
      - has_healthy=True  → list cut up to and including the first healthy anchor
      - has_healthy=False → all unhealthy candidates returned for second-attempt pass
    """

    def setUp(self):
        self.mock_w3 = MagicMock()
        self.mock_sender = MagicMock()
        self.mock_general_strategy = MagicMock()
        self.mock_csm_strategy = MagicMock()

        self.bot = DepositorBot(
            w3=self.mock_w3,
            sender=self.mock_sender,
            base_deposit_strategy=self.mock_general_strategy,
            csm_strategy=self.mock_csm_strategy,
            gas_price_calculator=MagicMock(),
            keys_api=MagicMock(),
            cl=MagicMock(),
        )

        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        # heartbeat fresh by default (initialized in __init__), can_deposit=True
        self.mock_w3.lido.deposit_security_module.can_deposit.return_value = True

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
        """Mark the module as having no quorum within QUORUM_RETENTION_MINUTES (cooldown expired)."""
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    # ─── Filters ────────────────────────────────────────────────────

    def test_non_0x02_modules_filtered(self):
        digests = [self._digest(1, '0xAddr1', 1)]
        result, has_healthy = self.bot._build_seed_list(digests, [50], [100])
        self.assertEqual(([], False), (result, has_healthy))

    def test_zero_allocation_filtered(self):
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        # module1: allocated=0 → skipped; module2: allocated=50 → candidate
        result, has_healthy = self.bot._build_seed_list(digests, [0, 50], [0, 100])
        self.assertEqual(([(2, '0xAddr2', 2, False)], True), (result, has_healthy))

    def test_module_not_in_whitelist_filtered(self):
        digests = [self._digest(4, '0xAddr4', 2)]
        result, has_healthy = self.bot._build_seed_list(digests, [50], [100])
        self.assertEqual(([], False), (result, has_healthy))

    # ─── Sort & selection ───────────────────────────────────────────

    def test_sort_by_current_stake_asc(self):
        # current_stake = new_allocations - allocated
        #   module1: 110 - 10 = 100
        #   module2:  70 - 50 =  20  ← lowest first
        #   module3:  80 - 30 =  50
        # All healthy → return only the lowest-stake module as anchor
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
            self._digest(3, '0xAddr3', 2),
        ]
        result, has_healthy = self.bot._build_seed_list(digests, [10, 50, 30], [110, 70, 80])
        self.assertEqual(([(2, '0xAddr2', 2, False)], True), (result, has_healthy))

    def test_single_healthy_returns_single(self):
        digests = [self._digest(1, '0xAddr1', 2)]
        result, has_healthy = self.bot._build_seed_list(digests, [50], [100])
        self.assertEqual(([(1, '0xAddr1', 2, False)], True), (result, has_healthy))

    def test_unhealthy_anchor_before_healthy(self):
        # current_stake: module1=20 (lowest, cooldown EXPIRED), module2=50 (healthy)
        # Unhealthy module1 is the unhealthy-anchor before the healthy module2.
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        self._set_no_recent_quorum(1)
        result, has_healthy = self.bot._build_seed_list(digests, [30, 50], [50, 100])
        self.assertEqual(
            ([(1, '0xAddr1', 2, False), (2, '0xAddr2', 2, False)], True),
            (result, has_healthy),
        )

    def test_cooldown_valid_treated_as_healthy(self):
        # Cooldown valid (heartbeat 25 min ago, < QUORUM_RETENTION_MINUTES=30) → healthy.
        # Module 1 returned as anchor even though no quorum is currently present.
        digests = [self._digest(1, '0xAddr1', 2)]
        self.bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=25)
        result, has_healthy = self.bot._build_seed_list(digests, [50], [100])
        self.assertEqual(([(1, '0xAddr1', 2, False)], True), (result, has_healthy))

    def test_all_unhealthy_returns_all_with_false_flag(self):
        # All cooldowns expired → no healthy anchor, but all candidates returned for
        # second-attempt pass (caller will concatenate with full_list).
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        self._set_no_recent_quorum(1)
        self._set_no_recent_quorum(2)
        # current_stake: module1=20, module2=50 → sorted [1, 2]
        result, has_healthy = self.bot._build_seed_list(digests, [30, 50], [50, 100])
        self.assertEqual(
            ([(1, '0xAddr1', 2, False), (2, '0xAddr2', 2, False)], False),
            (result, has_healthy),
        )

    def test_index_alignment_with_subset_whitelist(self):
        # SR has 4 0x02 modules, WHITELIST = [1, 3]. Allocations[]/new[] are indexed
        # by the full SR list, so misalignment would let module3 grab module2's slot.
        variables.DEPOSIT_MODULES_WHITELIST = [1, 3]
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),  # not whitelisted
            self._digest(3, '0xAddr3', 2),
            self._digest(4, '0xAddr4', 2),  # not whitelisted
        ]
        # current_stake for whitelisted: module1 = 70-50 = 20 (lowest); module3 = 80-30 = 50
        result, has_healthy = self.bot._build_seed_list(digests, [50, 999, 30, 999], [70, 999, 80, 999])
        self.assertEqual(([(1, '0xAddr1', 2, False)], True), (result, has_healthy))

    def test_empty_digests_returns_empty(self):
        result, has_healthy = self.bot._build_seed_list([], [], [])
        self.assertEqual(([], False), (result, has_healthy))


@pytest.mark.unit
class TestBuildFullList(unittest.TestCase):
    """
    Tests for _build_full_list. Returns (candidates, has_healthy):
      - has_healthy=True  → list cut up to and including the first healthy anchor
      - has_healthy=False → all unhealthy candidates returned for second-attempt pass

    Healthy criterion:
      - 0x02 (is_top_up=True) → can_top_up()
      - 0x01 (is_top_up=False) → _is_module_healthy() (can_deposit + cooldown)
    """

    def setUp(self):
        self.mock_w3 = MagicMock()
        self.mock_sender = MagicMock()

        self.bot = DepositorBot(
            w3=self.mock_w3,
            sender=self.mock_sender,
            base_deposit_strategy=MagicMock(),
            csm_strategy=MagicMock(),
            gas_price_calculator=MagicMock(),
            keys_api=MagicMock(),
            cl=MagicMock(),
        )

        variables.DEPOSIT_MODULES_WHITELIST = [1, 2, 3]
        variables.ENABLE_TOP_UP = True
        # heartbeat fresh by default (initialized in __init__), can_deposit=True
        self.mock_w3.lido.deposit_security_module.can_deposit.return_value = True

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
        """Mark module as having no quorum within QUORUM_RETENTION_MINUTES (cooldown expired)."""
        self.bot._module_last_heart_beat[module_id] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)

    # ─── Filters ────────────────────────────────────────────────────

    def test_module_not_in_whitelist_filtered(self):
        digests = [self._digest(4, '0xAddr4', 2)]
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True
        result, has_healthy = self.bot._build_full_list(digests, [50], [50])
        self.assertEqual(([], False), (result, has_healthy))

    def test_zero_allocation_filtered(self):
        digests = [
            self._digest(1, '0xAddr1', 1),
            self._digest(2, '0xAddr2', 1),
        ]
        result, has_healthy = self.bot._build_full_list(digests, [0, 50], [0, 100])
        self.assertEqual(([(2, '0xAddr2', 1, False)], True), (result, has_healthy))

    def test_enable_top_up_false_skips_0x02(self):
        variables.ENABLE_TOP_UP = False
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 1),
        ]
        result, has_healthy = self.bot._build_full_list(digests, [30, 50], [130, 70])
        self.assertEqual(([(2, '0xAddr2', 1, False)], True), (result, has_healthy))

    # ─── Sort ───────────────────────────────────────────────────────

    def test_sort_by_current_stake_asc(self):
        # current_stake = new_allocations - allocated
        #   module1: 110 - 10 = 100
        #   module2:  70 - 50 =  20  ← lowest first
        #   module3:  80 - 30 =  50
        # All healthy → return only the lowest-stake module as anchor
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
            self._digest(3, '0xAddr3', 2),
        ]
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True
        result, has_healthy = self.bot._build_full_list(digests, [10, 50, 30], [110, 70, 80])
        self.assertEqual(([(2, '0xAddr2', 2, True)], True), (result, has_healthy))

    # ─── 0x02 readiness (can_top_up) ────────────────────────────────

    def test_0x02_can_top_up_short_circuits(self):
        digests = [self._digest(1, '0xAddr1', 2)]
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True
        result, has_healthy = self.bot._build_full_list(digests, [50], [100])
        self.assertEqual(([(1, '0xAddr1', 2, True)], True), (result, has_healthy))

    def test_0x02_can_top_up_false_included_then_healthy_0x01(self):
        # 0x02 lowest-stake unhealthy (can_top_up=False) is appended as anchor;
        # iteration continues and the next module (0x01 healthy) becomes the real anchor.
        # Per design choice: unhealthy topup gets a doomed retry in the dispatcher.
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 1),
        ]
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = False
        # current_stake: module1=20 (lowest), module2=50
        result, has_healthy = self.bot._build_full_list(digests, [30, 50], [50, 100])
        self.assertEqual(
            ([(1, '0xAddr1', 2, True), (2, '0xAddr2', 1, False)], True),
            (result, has_healthy),
        )

    def test_all_0x02_can_top_up_false_returns_all_with_false_flag(self):
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),
        ]
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = False
        result, has_healthy = self.bot._build_full_list(digests, [30, 50], [130, 70])
        # current_stake: module1=100, module2=20 → sorted [2, 1]
        self.assertEqual(
            ([(2, '0xAddr2', 2, True), (1, '0xAddr1', 2, True)], False),
            (result, has_healthy),
        )

    # ─── 0x01 cooldown (heartbeat) ──────────────────────────────────

    def test_0x01_lowest_stake_healthy_returns_single(self):
        digests = [self._digest(1, '0xAddr1', 1)]
        result, has_healthy = self.bot._build_full_list(digests, [50], [100])
        self.assertEqual(([(1, '0xAddr1', 1, False)], True), (result, has_healthy))

    def test_0x01_no_recent_quorum_fallback_to_healthy_0x01(self):
        digests = [
            self._digest(1, '0xAddr1', 1),
            self._digest(2, '0xAddr2', 1),
        ]
        self._set_no_recent_quorum(1)
        # current_stake: module1=20 (lowest, unhealthy), module2=50 (healthy)
        result, has_healthy = self.bot._build_full_list(digests, [30, 50], [50, 100])
        self.assertEqual(
            ([(1, '0xAddr1', 1, False), (2, '0xAddr2', 1, False)], True),
            (result, has_healthy),
        )

    def test_0x01_no_recent_quorum_fallback_to_ready_0x02(self):
        digests = [
            self._digest(1, '0xAddr1', 1),
            self._digest(2, '0xAddr2', 2),
        ]
        self._set_no_recent_quorum(1)
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True
        # current_stake: module1=20 (lowest, unhealthy), module2=50 (healthy topup)
        result, has_healthy = self.bot._build_full_list(digests, [30, 50], [50, 100])
        self.assertEqual(
            ([(1, '0xAddr1', 1, False), (2, '0xAddr2', 2, True)], True),
            (result, has_healthy),
        )

    def test_all_unhealthy_returns_all_with_false_flag(self):
        # 0x01 without recent quorum + 0x02 without can_top_up → no anchor.
        # Both candidates returned for second-attempt pass.
        digests = [
            self._digest(1, '0xAddr1', 1),
            self._digest(2, '0xAddr2', 2),
        ]
        self._set_no_recent_quorum(1)
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = False
        result, has_healthy = self.bot._build_full_list(digests, [30, 50], [50, 100])
        # current_stake: module1=20, module2=50 → sorted [1, 2]
        self.assertEqual(
            ([(1, '0xAddr1', 1, False), (2, '0xAddr2', 2, True)], False),
            (result, has_healthy),
        )

    # ─── Index alignment regression ─────────────────────────────────

    def test_index_alignment_with_subset_whitelist(self):
        variables.DEPOSIT_MODULES_WHITELIST = [1, 3]
        digests = [
            self._digest(1, '0xAddr1', 2),
            self._digest(2, '0xAddr2', 2),  # not whitelisted
            self._digest(3, '0xAddr3', 2),
            self._digest(4, '0xAddr4', 2),  # not whitelisted
        ]
        self.mock_w3.lido.topup_gateway.can_top_up.return_value = True
        # current_stake for whitelisted: module1=20 (lowest); module3=50
        result, has_healthy = self.bot._build_full_list(digests, [50, 999, 30, 999], [70, 999, 80, 999])
        self.assertEqual(([(1, '0xAddr1', 2, True)], True), (result, has_healthy))

    def test_empty_digests_returns_empty(self):
        result, has_healthy = self.bot._build_full_list([], [], [])
        self.assertEqual(([], False), (result, has_healthy))


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


# ─── _prefered_modules orchestrator ────────────────────────────────


@pytest.mark.unit
def test_prefered_modules_no_depositable_ether_returns_empty(depositor_bot):
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=0)
    sr = depositor_bot.w3.lido.staking_router
    sr.get_deposit_allocations = Mock()

    assert depositor_bot._prefered_modules() == []
    sr.get_deposit_allocations.assert_not_called()


@pytest.mark.unit
def test_prefered_modules_seed_has_healthy_returns_only_seed(depositor_bot):
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100 * 10**18)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))

    seed = [(1, '0xA1', 2, False)]
    full = [(2, '0xA2', 1, False)]
    depositor_bot._build_seed_list = Mock(return_value=(seed, True))
    depositor_bot._build_full_list = Mock(return_value=(full, True))

    assert depositor_bot._prefered_modules() == seed
    depositor_bot._build_full_list.assert_not_called()


@pytest.mark.unit
def test_prefered_modules_seed_unhealthy_concats_full(depositor_bot):
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100 * 10**18)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))

    seed = [(1, '0xA1', 2, False)]  # all unhealthy → returned for second-attempt
    full = [(2, '0xA2', 1, False), (3, '0xA3', 2, True)]
    depositor_bot._build_seed_list = Mock(return_value=(seed, False))
    depositor_bot._build_full_list = Mock(return_value=(full, True))

    assert depositor_bot._prefered_modules() == seed + full


@pytest.mark.unit
def test_prefered_modules_seed_empty_returns_full(depositor_bot):
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100 * 10**18)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))

    full = [(2, '0xA2', 1, False)]
    depositor_bot._build_seed_list = Mock(return_value=([], False))
    depositor_bot._build_full_list = Mock(return_value=(full, True))

    assert depositor_bot._prefered_modules() == full


@pytest.mark.unit
def test_prefered_modules_both_empty_returns_empty(depositor_bot):
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100 * 10**18)
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(0, [], []))

    depositor_bot._build_seed_list = Mock(return_value=([], False))
    depositor_bot._build_full_list = Mock(return_value=([], False))

    assert depositor_bot._prefered_modules() == []


@pytest.mark.unit
def test_prefered_modules_quorum_called_only_for_whitelisted(depositor_bot):
    # WHITELIST = [1, 2] (set by depositor_bot fixture); module 4 must be ignored
    digest_1 = (0, 0, (1, '0xA1', 0, 0, 0, 0, '', 0, 0, 0, 0, 0, 0, 1, 0, 0), (0, 0, 0))
    digest_2 = (0, 0, (2, '0xA2', 0, 0, 0, 0, '', 0, 0, 0, 0, 0, 0, 1, 0, 0), (0, 0, 0))
    digest_4 = (0, 0, (4, '0xA4', 0, 0, 0, 0, '', 0, 0, 0, 0, 0, 0, 1, 0, 0), (0, 0, 0))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[digest_1, digest_2, digest_4])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=0)  # short-circuit before _build_*
    depositor_bot._get_quorum = Mock(return_value=None)
    depositor_bot._select_strategy = Mock(return_value=Mock())

    depositor_bot._prefered_modules()

    called_ids = sorted(c.args[0] for c in depositor_bot._get_quorum.call_args_list)
    assert called_ids == [1, 2]


@pytest.mark.unit
def test_prefered_modules_heartbeat_refreshed_on_truthy_quorum(depositor_bot):
    digest_1 = (0, 0, (1, '0xA1', 0, 0, 0, 0, '', 0, 0, 0, 0, 0, 0, 1, 0, 0), (0, 0, 0))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[digest_1])
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=0)
    depositor_bot._get_quorum = Mock(return_value=['msg'])  # truthy → refresh
    depositor_bot._select_strategy = Mock(return_value=Mock())

    depositor_bot._module_last_heart_beat[1] = datetime.now() - timedelta(minutes=variables.QUORUM_RETENTION_MINUTES + 1)
    before = depositor_bot._module_last_heart_beat[1]
    depositor_bot._prefered_modules()
    assert depositor_bot._module_last_heart_beat[1] > before


# ─── _execute_actual dispatcher ────────────────────────────────────


@pytest.mark.unit
def test_execute_actual_empty_modules_returns_false(depositor_bot):
    depositor_bot._prefered_modules = Mock(return_value=[])
    depositor_bot._deposit_to_module = Mock()
    depositor_bot._top_up_to_module = Mock()

    assert depositor_bot._execute_actual() is False
    depositor_bot._deposit_to_module.assert_not_called()
    depositor_bot._top_up_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_actual_first_succeeds_short_circuits(depositor_bot):
    m1 = (1, '0xA1', 1, False)
    m2 = (2, '0xA2', 1, False)
    depositor_bot._prefered_modules = Mock(return_value=[m1, m2])
    depositor_bot._deposit_to_module = Mock(return_value=True)
    depositor_bot._top_up_to_module = Mock()

    assert depositor_bot._execute_actual() is True
    depositor_bot._deposit_to_module.assert_called_once_with(1, True)


@pytest.mark.unit
def test_execute_actual_routes_seed_0x02_to_deposit_with_false_flag(depositor_bot):
    # 0x02 + is_top_up=False  →  seed deposit  →  legacy can_deposit_keys_based_on_ether
    m = (1, '0xA1', 2, False)
    depositor_bot._prefered_modules = Mock(return_value=[m])
    depositor_bot._deposit_to_module = Mock(return_value=True)
    depositor_bot._top_up_to_module = Mock()

    assert depositor_bot._execute_actual() is True
    depositor_bot._deposit_to_module.assert_called_once_with(1, False)
    depositor_bot._top_up_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_actual_routes_full_0x01_to_deposit_with_true_flag(depositor_bot):
    # 0x01 + is_top_up=False  →  full deposit  →  new can_deposit_keys_based_on_allocation
    m = (1, '0xA1', 1, False)
    depositor_bot._prefered_modules = Mock(return_value=[m])
    depositor_bot._deposit_to_module = Mock(return_value=True)
    depositor_bot._top_up_to_module = Mock()

    assert depositor_bot._execute_actual() is True
    depositor_bot._deposit_to_module.assert_called_once_with(1, True)
    depositor_bot._top_up_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_actual_routes_topup_to_top_up_module(depositor_bot):
    # 0x02 + is_top_up=True  →  topup path
    m = (1, '0xA1', 2, True)
    depositor_bot._prefered_modules = Mock(return_value=[m])
    depositor_bot._top_up_to_module = Mock(return_value=True)
    depositor_bot._deposit_to_module = Mock()

    assert depositor_bot._execute_actual() is True
    depositor_bot._top_up_to_module.assert_called_once_with(m)
    depositor_bot._deposit_to_module.assert_not_called()


@pytest.mark.unit
def test_execute_actual_seed_fails_falls_back_to_full(depositor_bot):
    # First seed deposit fails → continue iterating → full deposit succeeds
    seed = (1, '0xA1', 2, False)
    full = (2, '0xA2', 1, False)
    depositor_bot._prefered_modules = Mock(return_value=[seed, full])
    depositor_bot._deposit_to_module = Mock(side_effect=[False, True])

    assert depositor_bot._execute_actual() is True
    assert depositor_bot._deposit_to_module.call_count == 2
    assert [c.args for c in depositor_bot._deposit_to_module.call_args_list] == [(1, False), (2, True)]


@pytest.mark.unit
def test_execute_actual_deposit_fails_falls_back_to_topup(depositor_bot):
    # 0x01 unhealthy fail → 0x02 topup success
    deposit = (1, '0xA1', 1, False)
    topup = (2, '0xA2', 2, True)
    depositor_bot._prefered_modules = Mock(return_value=[deposit, topup])
    depositor_bot._deposit_to_module = Mock(return_value=False)
    depositor_bot._top_up_to_module = Mock(return_value=True)

    assert depositor_bot._execute_actual() is True
    depositor_bot._deposit_to_module.assert_called_once_with(1, True)
    depositor_bot._top_up_to_module.assert_called_once_with(topup)


@pytest.mark.unit
def test_execute_actual_all_fail_returns_false(depositor_bot):
    seed = (1, '0xA1', 2, False)
    full = (2, '0xA2', 1, False)
    topup = (3, '0xA3', 2, True)
    depositor_bot._prefered_modules = Mock(return_value=[seed, full, topup])
    depositor_bot._deposit_to_module = Mock(return_value=False)
    depositor_bot._top_up_to_module = Mock(return_value=False)

    assert depositor_bot._execute_actual() is False
    assert depositor_bot._deposit_to_module.call_count == 2
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
    depositor_bot._execute_actual = Mock()

    assert depositor_bot.execute(block_data) is True
    depositor_bot._execute_legacy.assert_called_once_with()
    depositor_bot._execute_actual.assert_not_called()


@pytest.mark.unit
def test_execute_sr_v4_routes_to_actual(depositor_bot, block_data):
    depositor_bot._check_balance = Mock()
    depositor_bot.w3.lido.staking_router.get_contract_version = Mock(return_value=4)
    depositor_bot._execute_legacy = Mock()
    depositor_bot._execute_actual = Mock(return_value=True)

    assert depositor_bot.execute(block_data) is True
    depositor_bot._execute_actual.assert_called_once_with()
    depositor_bot._execute_legacy.assert_not_called()


# ─── _top_up_to_module ─────────────────────────────────────────────


def _setup_topup_allocation(depositor_bot, module_id, allocation):
    """Set up mocks for the allocation re-query inside _top_up_to_module."""
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=100 * 10**18)
    digest = (0, 0, (module_id, '', 0, 0, 0, 0, '', 0, 0, 0, 0, 0, 0, 2, 0, 0), (0, 0, 0))
    depositor_bot.w3.lido.staking_router.get_all_staking_module_digests = Mock(return_value=[digest])
    depositor_bot.w3.lido.staking_router.get_deposit_allocations = Mock(return_value=(allocation, [allocation], [allocation]))


@pytest.mark.unit
def test_top_up_to_module_can_top_up_false_returns_false(depositor_bot):
    module = (1, '0xAddr1', 2, True)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=False)
    depositor_bot._get_module_type = Mock()
    depositor_bot._select_topup_strategy = Mock()

    assert depositor_bot._top_up_to_module(module) is False
    depositor_bot._get_module_type.assert_not_called()
    depositor_bot._select_topup_strategy.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_no_depositable_ether_returns_false(depositor_bot):
    module = (1, '0xAddr1', 2, True)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=0)
    depositor_bot._get_module_type = Mock()

    assert depositor_bot._top_up_to_module(module) is False
    depositor_bot._get_module_type.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_zero_allocation_returns_false(depositor_bot):
    module = (1, '0xAddr1', 2, True)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    _setup_topup_allocation(depositor_bot, 1, allocation=0)
    depositor_bot._get_module_type = Mock()

    assert depositor_bot._top_up_to_module(module) is False
    depositor_bot._get_module_type.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_unknown_module_type_returns_false(depositor_bot):
    module = (1, '0xAddr1', 2, True)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    _setup_topup_allocation(depositor_bot, 1, allocation=50)
    depositor_bot._get_module_type = Mock(return_value=b'unknown-type'.ljust(32, b'\x00'))
    depositor_bot._select_topup_strategy = Mock(return_value=None)

    assert depositor_bot._top_up_to_module(module) is False


@pytest.mark.unit
def test_top_up_to_module_gas_too_high_returns_false(depositor_bot):
    module = (1, '0xAddr1', 2, True)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    _setup_topup_allocation(depositor_bot, 1, allocation=50)
    depositor_bot._get_module_type = Mock(return_value=DepositorBot.MODULE_TYPE_CMV2)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=False)
    strategy.get_topup_candidates = Mock()
    depositor_bot._select_topup_strategy = Mock(return_value=strategy)

    assert depositor_bot._top_up_to_module(module) is False
    strategy.get_topup_candidates.assert_not_called()


@pytest.mark.unit
def test_top_up_to_module_no_candidates_returns_false(depositor_bot):
    module = (1, '0xAddr1', 2, True)
    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    _setup_topup_allocation(depositor_bot, 1, allocation=50)
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
    module = (1, '0xAddr1', 2, True)
    proof_data = ['proof']
    tx = Mock(name='tx')

    depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
    _setup_topup_allocation(depositor_bot, 1, allocation=50)
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
    module = (1, '0xAddr1', 2, True)

    original_config_limit = variables.MAX_VALIDATORS_PER_TOP_UP
    variables.MAX_VALIDATORS_PER_TOP_UP = config_limit
    try:
        depositor_bot.w3.lido.topup_gateway.can_top_up = Mock(return_value=True)
        _setup_topup_allocation(depositor_bot, 1, allocation=50)
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
@pytest.mark.parametrize('is_top_up_allocation', [True, False])
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
def test_depositor_deposit_to_module(
    depositor_bot, is_top_up_allocation, is_depositable, quorum, is_gas_price_ok, is_deposited_keys_amount_ok
):
    depositor_bot.w3.lido.deposit_security_module.can_deposit = Mock(return_value=is_depositable)
    depositor_bot._get_quorum = Mock(return_value=quorum)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=is_gas_price_ok)
    strategy.can_deposit_keys_based_on_ether = Mock(return_value=is_deposited_keys_amount_ok)
    strategy.can_deposit_keys_based_on_allocation = Mock(return_value=is_deposited_keys_amount_ok)
    depositor_bot._select_strategy = Mock(return_value=strategy)
    depositor_bot.prepare_and_send_tx = Mock()

    assert not depositor_bot._deposit_to_module(1, is_top_up_allocation)
    assert depositor_bot.prepare_and_send_tx.call_count == 0


@pytest.mark.unit
def test_deposit_to_module_top_up_allocation_true_uses_allocation_check(depositor_bot):
    """is_top_up_allocation=True (0x01 full deposit) must use can_deposit_keys_based_on_allocation."""
    depositor_bot.w3.lido.deposit_security_module.can_deposit = Mock(return_value=True)
    depositor_bot._get_quorum = Mock(return_value=True)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.can_deposit_keys_based_on_allocation = Mock(return_value=True)
    strategy.can_deposit_keys_based_on_ether = Mock(return_value=True)
    depositor_bot._select_strategy = Mock(return_value=strategy)
    depositor_bot.prepare_and_send_tx = Mock(return_value=True)

    assert depositor_bot._deposit_to_module(1, is_top_up_allocation=True)
    strategy.can_deposit_keys_based_on_allocation.assert_called_once_with(1)
    strategy.can_deposit_keys_based_on_ether.assert_not_called()


@pytest.mark.unit
def test_deposit_to_module_top_up_allocation_false_uses_ether_check(depositor_bot):
    """is_top_up_allocation=False (0x02 seed) must use legacy can_deposit_keys_based_on_ether."""
    depositor_bot.w3.lido.deposit_security_module.can_deposit = Mock(return_value=True)
    depositor_bot._get_quorum = Mock(return_value=True)
    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=True)
    strategy.can_deposit_keys_based_on_allocation = Mock(return_value=True)
    strategy.can_deposit_keys_based_on_ether = Mock(return_value=True)
    depositor_bot._select_strategy = Mock(return_value=strategy)
    depositor_bot.prepare_and_send_tx = Mock(return_value=True)

    assert depositor_bot._deposit_to_module(1, is_top_up_allocation=False)
    strategy.can_deposit_keys_based_on_ether.assert_called_once_with(1)
    strategy.can_deposit_keys_based_on_allocation.assert_not_called()


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
