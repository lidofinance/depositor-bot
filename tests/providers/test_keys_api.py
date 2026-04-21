import os
from dataclasses import asdict

import pytest
import variables
from providers.keys_api import KeysAPIClient, LidoKey

# devnet 2
DEVNET_MODULE_ADDRESSES = {
    1: '0x2AA77A8837ee41a2635307590Ee540248FBFE236',
    2: '0xe9410845D15D9217eB583Cf03a6e398fd813C6bb',
    3: '0x71139076EDD286dd36Cb763E332FA732438EbB69',
    4: '0x9539D751255fF3b04176C74EAdC5c253C2828C1B',
}


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


@pytest.fixture
def expected_module_address(keys_api_test_module_id: int) -> str:
    try:
        return DEVNET_MODULE_ADDRESSES[keys_api_test_module_id]
    except KeyError as error:
        raise pytest.skip(f'No expected devnet module address configured for module {keys_api_test_module_id}.') from error


def _print_keys_sample(keys: list[LidoKey], limit: int = 3) -> None:
    sample = []
    for key in keys[:limit]:
        data = asdict(key)
        data['depositSignature'] = f"{data['depositSignature'][:18]}..."
        data['key'] = f"{data['key'][:18]}..."
        sample.append(data)
    print(f'Fetched {len(keys)} used keys. Sample: {sample}')


def _print_kapi_curl(host: str, module_id: int) -> None:
    host = host.rstrip('/')
    endpoint = f'v1/modules/{module_id}/operators/keys'
    url = f'{host}/{endpoint}?used=true'
    print(f'KAPI curl: curl "{url}"')


@pytest.mark.integration
def test_get_module_used_keys(
    keys_api_client: KeysAPIClient,
    keys_api_test_module_id: int,
    expected_module_address: str,
):
    keys = keys_api_client.get_module_used_keys(keys_api_test_module_id)

    assert isinstance(keys, list)
    assert keys
    assert all(isinstance(key, LidoKey) for key in keys)
    assert all(key.used for key in keys)
    assert all(key.key.startswith('0x') for key in keys)
    assert all(key.key == key.key.lower() for key in keys)
    assert all(key.moduleAddress.startswith('0x') for key in keys)
    assert all(len(key.moduleAddress) == 42 for key in keys)
    assert {key.moduleAddress.lower() for key in keys} == {expected_module_address.lower()}


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
        assert all(key.used for key in operator_keys)


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
