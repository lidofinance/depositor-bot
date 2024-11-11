import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from blockchain.deposit_strategy.deposit_module_recommender import DepositModuleRecommender


class TestDepositModuleRecommender(unittest.TestCase):
    def setUp(self):
        # Create a mock Web3 instance with necessary Lido staking_router and deposit_security_module attributes
        self.mock_w3 = MagicMock()
        self.recommender = DepositModuleRecommender(w3=self.mock_w3)

    @patch('blockchain.deposit_strategy.deposit_module_recommender.datetime')
    def test_set_timeout(self, mock_datetime):
        """Test setting a timeout for a module."""
        mock_datetime.now.return_value = datetime(2023, 10, 1, 12, 0, 0)
        module_id = 1

        self.recommender.set_timeout(module_id)
        self.assertIn(module_id, self.recommender._module_timeouts)
        self.assertEqual(self.recommender._module_timeouts[module_id], mock_datetime.now())

    def test_reset_timeout(self):
        """Test resetting a timeout for a module."""
        module_id = 1
        self.recommender._module_timeouts[module_id] = datetime.now()
        self.recommender.reset_timeout(module_id)
        self.assertNotIn(module_id, self.recommender._module_timeouts)

    @patch('blockchain.deposit_strategy.deposit_module_recommender.datetime')
    def test_is_timeout_passed(self, mock_datetime):
        """Test that _is_timeout_passed correctly identifies passed timeouts."""
        mock_datetime.now.return_value = datetime(2023, 10, 1, 12, 10, 0)
        module_id = 1
        self.recommender._module_timeouts[module_id] = mock_datetime.now() - timedelta(minutes=15)

        # Timeout of 10 minutes for module_id 1 should be exceeded
        self.assertTrue(self.recommender._is_timeout_passed(module_id))

    def test_prioritize_modules(self):
        """Test prioritization of modules based on validator count."""
        modules = [
            ['ModuleA', 'info', [1], [5, 10]],  # Difference: 5
            ['ModuleB', 'info', [2], [15, 20]],  # Difference: 5
            ['ModuleC', 'info', [3], [1, 5]],  # Difference: 4
        ]
        prioritized = self.recommender.prioritize_modules(modules)
        self.assertEqual(prioritized, [3, 1, 2])  # Module C has smallest difference, followed by A and B

    def test_get_preferred_to_deposit_modules(self):
        """Test retrieval of depositable modules based on whitelist and active status."""
        whitelist_modules = [1, 2]
        self.mock_w3.lido.staking_router.get_staking_module_ids.return_value = [1, 2, 3]
        self.mock_w3.lido.staking_router.get_staking_module_digests.return_value = [
            ['ModuleA', 'info', [1], [10, 5]],  # Module 1, whitelisted and active
            ['ModuleB', 'info', [2], [20, 15]],  # Module 2, whitelisted but inactive
            ['ModuleC', 'info', [3], [5, 1]],  # Module 3, not whitelisted
        ]

        # Set module activity and deposit capability
        self.mock_w3.lido.staking_router.is_staking_module_active.side_effect = lambda module_id: module_id != 2
        self.mock_w3.lido.deposit_security_module.can_deposit.side_effect = lambda module_id: module_id == 1

        preferred_modules = self.recommender.get_preferred_to_deposit_modules(whitelist_modules)
        self.assertEqual(preferred_modules, [1])

    @patch('blockchain.deposit_strategy.deposit_module_recommender.datetime')
    def test_depositable_filter_with_timeout(self, mock_datetime):
        """Test the depositable filter with module timeout handling."""
        mock_datetime.now.return_value = datetime(2023, 10, 1, 12, 0, 0)
        whitelist_modules = [1]
        module = ['ModuleA', 'info', [1], [10, 5]]

        # Set up a timeout that has not yet expired
        self.recommender.set_timeout(1)
        self.recommender._module_timeouts[1] = mock_datetime.now() - timedelta(minutes=5)
        self.assertFalse(self.recommender._get_module_depositable_filter(whitelist_modules)(module))

        # Update time to simulate expiration of timeout
        self.recommender._module_timeouts[1] = mock_datetime.now() - timedelta(minutes=15)
        self.assertTrue(self.recommender._get_module_depositable_filter(whitelist_modules)(module))
