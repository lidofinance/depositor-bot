import importlib
import json

import pytest

import variables

pytestmark = pytest.mark.unit

TEST_KEY = '0x' + '1' * 64
SECRET_NAMES = (
    'WALLET_PRIVATE_KEY',
    'AUCTION_BUNDLER_PRIVATE_KEY',
    'WEB3_RPC_ENDPOINTS',
    'ONCHAIN_TRANSPORT_RPC_ENDPOINTS',
    'CL_API_URLS',
    'KEYS_API_URL',
)


@pytest.fixture
def load_variables(monkeypatch):
    """Reload the variables module with extra env; the module is reloaded with the original env afterwards."""

    def load(**env):
        with monkeypatch.context() as mp:
            for name, value in env.items():
                if value is None:
                    mp.delenv(name, raising=False)
                else:
                    mp.setenv(name, value)
            return importlib.reload(variables)

    yield load
    importlib.reload(variables)


def test_private_key_from_file(load_variables, tmp_path):
    key_file = tmp_path / 'wallet-private-key'
    key_file.write_text(TEST_KEY + '\n')

    loaded = load_variables(WALLET_PRIVATE_KEY_FILE=str(key_file), WALLET_PRIVATE_KEY=None)

    assert loaded.WALLET_PRIVATE_KEY == TEST_KEY
    assert loaded.ACCOUNT is not None
    assert loaded.PUBLIC_ENV_VARS['ACCOUNT'] == loaded.ACCOUNT.address
    assert loaded.PUBLIC_ENV_VARS['WALLET_PRIVATE_KEY_FILE'] == str(key_file)


def test_empty_private_key_file_gives_dry_mode(load_variables, tmp_path):
    key_file = tmp_path / 'wallet-private-key'
    key_file.write_text('')

    loaded = load_variables(WALLET_PRIVATE_KEY_FILE=str(key_file), WALLET_PRIVATE_KEY=TEST_KEY)

    assert loaded.ACCOUNT is None
    assert loaded.PUBLIC_ENV_VARS['ACCOUNT'] == ''


def test_missing_private_key_file_fails_at_startup(load_variables, tmp_path):
    with pytest.raises(ValueError, match='WALLET_PRIVATE_KEY_FILE'):
        load_variables(WALLET_PRIVATE_KEY_FILE=str(tmp_path / 'missing'))


def test_auction_bundler_key_from_file(load_variables, tmp_path):
    key_file = tmp_path / 'auction-key'
    key_file.write_text(TEST_KEY + '\n')

    loaded = load_variables(AUCTION_BUNDLER_PRIVATE_KEY_FILE=str(key_file), AUCTION_BUNDLER_PRIVATE_KEY=None)

    assert loaded.AUCTION_BUNDLER_PRIVATE_KEY == TEST_KEY


def test_auction_bundler_key_keeps_legacy_env_name(load_variables):
    loaded = load_variables(AUCTION_BUNDLER_PRIVATE_KEY=None, AUCTION_BUNDLER_PRIVATE_KEY_FILE=None, FLASHBOT_SIGNATURE=TEST_KEY)

    assert loaded.AUCTION_BUNDLER_PRIVATE_KEY == TEST_KEY


@pytest.mark.parametrize('value', ['', None])
def test_empty_auction_bundler_key_turns_relay_signing_off(load_variables, tmp_path, value):
    # Only an unset variable falls back to the legacy FLASHBOT_SIGNATURE; an empty value or an empty file does not.
    env = {'FLASHBOT_SIGNATURE': TEST_KEY, 'AUCTION_BUNDLER_PRIVATE_KEY': value, 'AUCTION_BUNDLER_PRIVATE_KEY_FILE': None}
    if value is None:
        key_file = tmp_path / 'auction-key'
        key_file.write_text('\n')
        env['AUCTION_BUNDLER_PRIVATE_KEY_FILE'] = str(key_file)

    assert load_variables(**env).AUCTION_BUNDLER_PRIVATE_KEY == ''


def test_keys_api_url_is_secret(load_variables, tmp_path):
    url = 'https://user:kapi-password@kapi.example/'
    url_file = tmp_path / 'kapi'
    url_file.write_text(url + '\n')

    loaded = load_variables(KEYS_API_URL_FILE=str(url_file), KEYS_API_URL=None)

    assert url == loaded.KEYS_API_URL
    # PUBLIC_ENV_VARS goes unmasked into the build_info metric labels.
    assert 'kapi-password' not in json.dumps(loaded.PUBLIC_ENV_VARS, default=str)


def test_keys_api_url_unset_is_empty(load_variables):
    assert load_variables(KEYS_API_URL=None, KEYS_API_URL_FILE=None).KEYS_API_URL == ''


@pytest.mark.parametrize('name', ['WEB3_RPC_ENDPOINTS', 'ONCHAIN_TRANSPORT_RPC_ENDPOINTS', 'CL_API_URLS'])
def test_url_list_from_file(load_variables, tmp_path, name):
    urls_file = tmp_path / name.lower()
    urls_file.write_text('https://node.example/one, https://node.example/two,\n')

    loaded = load_variables(**{f'{name}_FILE': str(urls_file), name: 'https://node.example/env'})

    assert getattr(loaded, name) == ['https://node.example/one', 'https://node.example/two']
    assert loaded.PUBLIC_ENV_VARS[f'{name}_FILE'] == str(urls_file)


def test_env_start_still_works(load_variables):
    loaded = load_variables(
        WALLET_PRIVATE_KEY=TEST_KEY,
        WALLET_PRIVATE_KEY_FILE=None,
        WEB3_RPC_ENDPOINTS='https://rpc.example/env',
        WEB3_RPC_ENDPOINTS_FILE=None,
    )

    assert loaded.ACCOUNT is not None
    assert loaded.WEB3_RPC_ENDPOINTS == ['https://rpc.example/env']
    assert loaded.PUBLIC_ENV_VARS['WALLET_PRIVATE_KEY_FILE'] == ''


def test_every_secret_is_private_and_has_a_file_path_in_the_dump():
    for name in SECRET_NAMES:
        assert name in variables.PRIVATE_ENV_VARS
        assert name not in variables.PUBLIC_ENV_VARS
        assert f'{name}_FILE' in variables.PUBLIC_ENV_VARS
