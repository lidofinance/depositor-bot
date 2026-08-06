"""Cache→genesis conversion. Offline: the fixtures are trimmed real cache entries."""

import pytest

from tests.fork_snapshot import CHAIN_ID_HOODI, _code_hex, cache_to_genesis

FORK_BLOCK = '0x33581d'  # 3364893
GATEWAY = '0x10dbeb3367876826d00d21718d1d893e0fbd2956'
LOCATOR = '0xe2ef9536daaaebff5b1c130957ab3e80056b06d8'


@pytest.fixture
def cache() -> dict:
    return {
        'meta': {
            'block_env': {
                'number': FORK_BLOCK,
                'timestamp': '0x6a749750',
                'gas_limit': 60000000,
                'basefee': 901568626,
                'beneficiary': '0x0000000000000000000000000000000000000000',
                'prevrandao': '0x' + 'fb' * 32,
            }
        },
        'accounts': {
            GATEWAY: {
                'balance': '0x0',
                'nonce': 1,
                # 3 bytes of real code + the 33 bytes of jumpdest padding revm appends.
                'code': {'LegacyAnalyzed': {'bytecode': '0x608060' + '00' * 33, 'original_len': 3, 'jump_table': '0x00'}},
            },
            LOCATOR: {'balance': '0x0', 'nonce': 1, 'code': {'LegacyAnalyzed': {'bytecode': '0x6080' + '00' * 33, 'original_len': 2}}},
            '0x14dc79964da2c08b23698b3d3cc7ca32193d9955': {
                'balance': '0x21e19e0c9bab2400000',
                'nonce': 3,
                'code': {'Eip7702': {'delegated_address': '0x' + 'ab' * 20, 'version': 0, 'raw': '0xef0100' + 'ab' * 20}},
            },
        },
        'storage': {
            # An address-valued slot: 20 bytes in the cache, must become a full word.
            LOCATOR: {'0x' + '11' * 32: '0xa519be1bbfd95445cedfea56c12ab0b28330cc2f'}
        },
        'block_hashes': {FORK_BLOCK: '0x' + 'cd' * 32},
    }


@pytest.mark.unit
def test_genesis_starts_at_the_forked_height(cache):
    """The whole reason for the genesis format: contracts subtract stored block numbers, so a chain
    rebased to 0 makes `block.number - lastDepositBlock` underflow and revert."""
    genesis = cache_to_genesis(cache)
    assert genesis['number'] == FORK_BLOCK


@pytest.mark.unit
def test_genesis_keeps_the_forked_timestamp(cache):
    """Beacon-root reads are keyed by timestamp; a reset clock cannot resolve the 4788 ring buffer."""
    assert cache_to_genesis(cache)['timestamp'] == '0x6a749750'


@pytest.mark.unit
def test_legacy_code_is_truncated_to_original_length(cache):
    """revm pads analysed bytecode with 33 zero bytes. Keeping them changes every code hash."""
    alloc = cache_to_genesis(cache)['alloc']
    assert alloc[GATEWAY]['code'] == '0x608060'
    assert alloc[LOCATOR]['code'] == '0x6080'


@pytest.mark.unit
def test_eip7702_delegation_designator_is_preserved(cache):
    """anvil's dev accounts carry 7702 delegations on public testnets — their keys are public."""
    assert cache_to_genesis(cache)['alloc']['0x14dc79964da2c08b23698b3d3cc7ca32193d9955']['code'] == '0xef0100' + 'ab' * 20


@pytest.mark.unit
def test_storage_values_are_widened_to_full_words(cache):
    """Genesis storage is a fixed 32-byte map; an unpadded value reads as a much smaller number."""
    storage = cache_to_genesis(cache)['alloc'][LOCATOR]['storage']
    key, value = next(iter(storage.items()))
    assert len(key) == 66 and len(value) == 66
    assert value == '0x' + '0' * 24 + 'a519be1bbfd95445cedfea56c12ab0b28330cc2f'


@pytest.mark.unit
def test_accounts_without_code_are_kept_without_a_code_key(cache):
    cache['accounts']['0x' + '99' * 20] = {'balance': '0x1', 'nonce': 0, 'code': None}
    entry = cache_to_genesis(cache)['alloc']['0x' + '99' * 20]
    assert 'code' not in entry
    assert entry['balance'] == '0x1'


@pytest.mark.unit
def test_chain_id_defaults_to_hoodi_and_can_be_overridden(cache):
    assert cache_to_genesis(cache)['config']['chainId'] == CHAIN_ID_HOODI
    assert cache_to_genesis(cache, 1)['config']['chainId'] == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    'code_field,expected',
    [
        (None, '0x'),
        ('0xdeadbeef', '0xdeadbeef'),
        ({'LegacyRaw': '0xdeadbeef'}, '0xdeadbeef'),
        ({'LegacyAnalyzed': {'bytecode': '0xdeadbeef' + '00' * 33, 'original_len': 4}}, '0xdeadbeef'),
        ({'LegacyAnalyzed': {'bytecode': '0xdeadbeef'}}, '0xdeadbeef'),  # no original_len → as-is
    ],
)
def test_code_hex_variants(code_field, expected):
    assert _code_hex(code_field) == expected
