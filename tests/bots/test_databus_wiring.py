"""Each bot must receive both council generations of its message type through the real Data Bus provider.

The autouse `stub_databus` fixture replaces the provider in all other bot tests, so a wrong parser list
or schema in a bot's constructor would keep them green. Here only the Gnosis w3 is stubbed.
"""

from unittest import mock
from unittest.mock import MagicMock, Mock

import pytest
from web3 import Web3

from bots.depositor import DepositorBot
from bots.pauser import PauserBot
from bots.unvetter import UnvetterBot
from transport.msg_providers.onchain_transport import (
    DepositV1Parser,
    DepositV2Parser,
    OnchainTransportProvider,
    PauseV3Parser,
    PauseV4Parser,
    UnvetV1Parser,
    UnvetV2Parser,
)

_DELEGATE = Web3.to_checksum_address('0x1be2A219CBD0F18B825a4dDd580F7b3B33Bacb41')
_GUARDIAN = Web3.to_checksum_address('0x2C44CdDdB6a900fa2b585dd299e03d12FA4293BC')
_HASH = b'\x11' * 32
_VERSION = (b'\0' * 32,)
_COMPACT_SIGNATURE = (b'\0' * 32, b'\0' * 32)
_FLAT_SIGNATURE = bytes(65)


@pytest.fixture(autouse=True)
def stub_databus(web3_lido_unit):
    """Overrides the conftest stub: the real provider runs, only its Gnosis w3 is replaced."""
    web3_lido_unit.lido.get_guardian_delegates = Mock(return_value={_DELEGATE: _GUARDIAN})
    web3_lido_unit.lido.delegation = None
    web3_lido_unit.eth.get_block = Mock()
    with (
        mock.patch.object(OnchainTransportProvider, 'create_onchain_transport_w3', return_value=web3_lido_unit),
        mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock, return_value=100),
        mock.patch('web3.eth.Eth.block_number', new_callable=mock.PropertyMock, return_value=1000),
    ):
        yield


def _log(w3: Web3, parser, payload: tuple) -> dict:
    """A raw anonymous Data Bus `Message` log, decoded by the real parser path."""
    return {
        'address': '0x0000000000000000000000000000000000000000',
        'topics': [w3.keccak(text=parser.message_abi), bytes(12) + bytes.fromhex(_DELEGATE[2:])],
        'data': w3.codec.encode(['bytes'], [w3.codec.encode([parser(w3)._schema], [payload])]),
        'blockHash': _HASH,
        'blockNumber': 1,
        'transactionHash': _HASH,
        'transactionIndex': 0,
        'logIndex': 0,
    }


def _make_pauser(w3):
    return PauserBot(w3)


def _make_unvetter(w3):
    bot = UnvetterBot(w3)
    bot.prepare_transport_bus()
    return bot


def _make_depositor(w3):
    with mock.patch.object(DepositorBot, '_build_consolidation_indexer', return_value=MagicMock()):
        return DepositorBot(w3, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())


_OPERATOR_IDS = (0).to_bytes(8, 'big')
_VETTED_KEYS = (0).to_bytes(16, 'big')

CASES = [
    pytest.param(
        _make_pauser,
        'pause',
        [
            (PauseV3Parser, (10, _HASH, _COMPACT_SIGNATURE, _VERSION)),
            (PauseV4Parser, (11, _HASH, _FLAT_SIGNATURE, _VERSION)),
        ],
        id='pauser',
    ),
    pytest.param(
        _make_unvetter,
        'unvet',
        [
            (UnvetV1Parser, (10, _HASH, 1, 5, _OPERATOR_IDS, _VETTED_KEYS, _COMPACT_SIGNATURE, _VERSION)),
            (UnvetV2Parser, (11, _HASH, 1, 5, _OPERATOR_IDS, _VETTED_KEYS, _FLAT_SIGNATURE, _VERSION)),
        ],
        id='unvetter',
    ),
    pytest.param(
        _make_depositor,
        'deposit',
        [
            (DepositV1Parser, (10, _HASH, _HASH, 1, 5, _COMPACT_SIGNATURE, _VERSION)),
            (DepositV2Parser, (11, _HASH, _HASH, 1, 5, _FLAT_SIGNATURE, _VERSION)),
        ],
        id='depositor',
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize('make_bot, message_type, events', CASES)
def test_bot_receives_both_council_generations(web3_lido_unit, make_bot, message_type, events):
    logs = [_log(web3_lido_unit, parser, payload) for parser, payload in events]
    web3_lido_unit.eth.get_logs = Mock(return_value=logs)

    bot = make_bot(web3_lido_unit)
    # MessageStorage.messages is class-level; give this instance its own list so nothing leaks.
    bot.message_storage.clear()
    messages = bot.message_storage.get_messages_and_actualize(lambda _: True)
    bot.message_storage.clear()

    assert [(m['type'], m['blockNumber']) for m in messages] == [(message_type, 10), (message_type, 11)]
    assert all(m['guardianAddress'] == _GUARDIAN for m in messages)
