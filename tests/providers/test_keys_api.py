import os

import pytest
import variables
from providers.keys_api import KeysAPIClient, LidoKey


@pytest.fixture(autouse=True)
def devnet_only():
    if os.getenv('KEYS_API_TEST_NETWORK', '').lower() != 'devnet2':
        pytest.skip('KAPI integration tests run only against devnet. Set KEYS_API_TEST_NETWORK=devnet.')


@pytest.fixture
def keys_api_client(request) -> KeysAPIClient:
    params = getattr(request, 'param', {})
    host = params.get('host', variables.KEYS_API_URL)
    if not host:
        pytest.skip('KEYS_API_URL is not configured.')
    print(f'Using KAPI host: {host}')

    return KeysAPIClient(
        host=host,
        request_timeout=30,
        retry_total=3,
        retry_backoff_factor=1,
    )


@pytest.fixture
def keys_api_test_module_id() -> int:
    return int(os.getenv('KEYS_API_TEST_MODULE_ID', '1'))


def _print_keys_sample(keys: list[LidoKey], limit: int = 3) -> None:
    sample = []
    for key in keys[:limit]:
        data = key._asdict()
        data['key'] = f"{data['key'][:18]}..."
        sample.append(data)
    print(f'Fetched {len(keys)} used keys. Sample: {sample}')


@pytest.mark.integration
def test_get_module_used_keys(
    keys_api_client: KeysAPIClient,
    keys_api_test_module_id: int,
):
    keys = keys_api_client.get_module_used_keys(keys_api_test_module_id)

    assert isinstance(keys, list)
    assert keys
    assert all(isinstance(key, LidoKey) for key in keys)
    assert all(key.key.startswith('0x') for key in keys)
    assert all(key.key == key.key.lower() for key in keys)


@pytest.mark.integration
def test_get_module_operator_used_keys(keys_api_client: KeysAPIClient, keys_api_test_module_id: int):
    all_keys = keys_api_client.get_module_used_keys(keys_api_test_module_id)
    operator_ids = sorted({key.operatorIndex for key in all_keys})[:3]
    if not operator_ids:
        pytest.skip(f'No operators with used keys found for module {keys_api_test_module_id}.')

    keys_by_operator = keys_api_client.get_module_operator_used_keys(keys_api_test_module_id, operator_ids)

    assert set(keys_by_operator) == set(operator_ids)
    for operator_id, operator_keys in keys_by_operator.items():
        assert all(key.operatorIndex == operator_id for key in operator_keys)


@pytest.mark.integration
def test_grouped_operator_keys_match_flat_used_keys(keys_api_client: KeysAPIClient, keys_api_test_module_id: int):
    all_keys = keys_api_client.get_module_used_keys(keys_api_test_module_id)
    operator_ids = sorted({key.operatorIndex for key in all_keys})[:3]
    if not operator_ids:
        pytest.skip(f'No operators with used keys found for module {keys_api_test_module_id}.')

    keys_by_operator = keys_api_client.get_module_operator_used_keys(keys_api_test_module_id, operator_ids)

    expected = sorted((key.index, key.operatorIndex, key.key) for key in all_keys if key.operatorIndex in operator_ids)
    grouped = sorted((key.index, key.operatorIndex, key.key) for operator_keys in keys_by_operator.values() for key in operator_keys)

    assert grouped == expected


@pytest.mark.integration
def test_get_chain_id_with_provider(keys_api_client: KeysAPIClient):
    chain_id = keys_api_client._get_chain_id_with_provider(0)

    assert chain_id > 0
