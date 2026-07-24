from unittest.mock import Mock, patch

import pytest
from providers.keys_api import KeysAPIClient


@pytest.mark.unit
def test_get_module_used_keys_reports_freshness_from_meta():
    client = KeysAPIClient(host='http://kapi.example')
    data = {'keys': [{'key': '0xAA', 'index': 0, 'operatorIndex': 1}]}
    meta = {'meta': {'elBlockSnapshot': {'blockNumber': 123, 'blockHash': '0x1', 'timestamp': 1000, 'lastChangedBlockHash': '0x2'}}}
    client._get = Mock(return_value=(data, meta))

    with (
        patch('providers.keys_api.KEYS_API_BLOCK_NUMBER') as block_number_gauge,
        patch('providers.keys_api.KEYS_API_BLOCK_AGE_SECONDS') as block_age_gauge,
        patch('providers.keys_api.time') as time_module,
    ):
        time_module.time.return_value = 1100
        keys = client.get_module_used_keys(1)

    assert len(keys) == 1
    block_number_gauge.set.assert_called_once_with(123)
    block_age_gauge.set.assert_called_once_with(100)


@pytest.mark.unit
def test_report_freshness_is_defensive_to_missing_meta():
    """A KAPI schema change (or a response with no meta at all) must not break the deposit path."""
    with (
        patch('providers.keys_api.KEYS_API_BLOCK_NUMBER') as block_number_gauge,
        patch('providers.keys_api.KEYS_API_BLOCK_AGE_SECONDS') as block_age_gauge,
    ):
        KeysAPIClient._report_freshness({})

    block_number_gauge.set.assert_not_called()
    block_age_gauge.set.assert_not_called()
