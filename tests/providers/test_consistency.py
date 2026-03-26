# pylint: disable=protected-access
import unittest
from typing import Any
from unittest.mock import Mock

import pytest

from providers.consistency import InconsistentProviders, NotHealthyProvider, ProviderConsistencyModule


@pytest.mark.unit
class TestProviderConsistencyModule(unittest.TestCase):
    def setUp(self):
        class TestConsistencyModule(ProviderConsistencyModule):
            def get_all_providers(self) -> list[Any]:
                return ['provider1', 'provider2', 'provider3']

            def _get_chain_id_with_provider(self, provider_index: int) -> int:
                return 1

        self.provider_module = TestConsistencyModule()

    def test_check_providers_consistency_success(self):
        self.provider_module._get_chain_id_with_provider = Mock(side_effect=[1, 1, 1])

        result = self.provider_module.check_providers_consistency()

        self.assertEqual(result, 1)

    def test_check_providers_consistency_inconsistent(self):
        self.provider_module._get_chain_id_with_provider = Mock(side_effect=[1, 2, 1])

        with self.assertRaises(InconsistentProviders) as context:
            self.provider_module.check_providers_consistency()

        self.assertIn('Different chain ids detected', str(context.exception))

    def test_check_providers_consistency_not_healthy(self):
        self.provider_module._get_chain_id_with_provider = Mock(side_effect=[1, Exception('Provider not responding'), 1])

        with self.assertRaises(NotHealthyProvider) as context:
            self.provider_module.check_providers_consistency()

        self.assertIn('Provider [1] does not responding', str(context.exception))

    def test_check_providers_consistency_no_providers(self):
        class NoProvidersModule(ProviderConsistencyModule):
            def get_all_providers(self) -> list[Any]:
                return []

            def _get_chain_id_with_provider(self, provider_index: int) -> int:
                return 1

        no_providers_module = NoProvidersModule()
        result = no_providers_module.check_providers_consistency()
        self.assertIsNone(result)
