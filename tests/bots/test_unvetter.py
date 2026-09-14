import logging
from unittest.mock import Mock

import pytest

from bots.unvetter import UnvetterBot
from cryptography.verify_signature import compute_vs
from transport.msg_providers.onchain_transport import build_unvet_message
from transport.msg_types.common import get_messages_sign_filter
from transport.msg_types.unvet import UnvetMessage
from utils.bytes import from_hex_string_to_bytes

# WARNING: These accounts, and their private keys, are publicly known.
COUNCIL_ADDRESS = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8'
COUNCIL_PK = '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d'


def get_unvet_message(web3) -> UnvetMessage:
    latest = web3.eth.get_block('latest')
    block_number = latest.number

    prefix = web3.lido.deposit_security_module.get_unvet_message_prefix()
    nonce = web3.lido.staking_router.functions.getStakingModuleNonce(1).call()

    operator_ids = from_hex_string_to_bytes('0x1234')
    vetted_keys_by_operator = from_hex_string_to_bytes('0001')

    msg_hash = web3.solidity_keccak(
        ['bytes32', 'uint256', 'bytes32', 'uint256', 'uint256', 'bytes', 'bytes'],
        [
            prefix,
            block_number,
            latest.hash,
            1,
            nonce,
            operator_ids,
            vetted_keys_by_operator,
        ],
    )
    signed = web3.eth.account._sign_hash(msg_hash, private_key=COUNCIL_PK)

    unvet_message = build_unvet_message(
        block_number=block_number,
        block_hash=latest.hash,
        guardian=COUNCIL_ADDRESS,
        staking_module_id=1,
        nonce=nonce,
        operator_ids=operator_ids,
        vetted_keys_by_operator=vetted_keys_by_operator,
        r=signed.r.to_bytes(32, 'big'),
        vs=from_hex_string_to_bytes(compute_vs(signed.v, '0x' + signed.s.to_bytes(32, 'big').hex())),
        version=b'0x1',
    )
    prefix = web3.lido.deposit_security_module.get_unvet_message_prefix()
    assert list(filter(get_messages_sign_filter(prefix), [unvet_message]))

    return unvet_message


@pytest.mark.skip(
    reason='Legacy v4 guardian-signed fixtures fail against the now-v5 Hoodi fork (delegation active). '
    'Needs v5 message fixtures (guardian folded into the digest, signed by the delegate). '
    'See docs/edf-guardian-delegation.md.'
)
@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [
        {
            'block': None,  # Fork from latest block
        }
    ],
    indirect=['web3_provider_integration'],
)
def test_unvetter(web3_provider_integration, web3_lido_integration, caplog):
    latest = web3_lido_integration.eth.get_block('latest')

    ub = UnvetterBot(web3_lido_integration)
    ub.execute(latest)
    ub._get_message_actualize_filter = Mock(return_value=lambda x: True)

    ub.execute(latest)
    web3_lido_integration.lido.deposit_security_module.get_guardians = Mock(return_value=[COUNCIL_ADDRESS])
    ub.message_storage.messages = [get_unvet_message(web3_lido_integration)]

    caplog.set_level(logging.INFO)

    ub.execute(latest)

    assert [msg for msg in caplog.messages if 'Build `unvetSigningKeys(' in msg]
    assert ub.message_storage.messages

    web3_lido_integration.lido.staking_router.get_staking_module_nonce = Mock(return_value=ub.message_storage.messages[0]['nonce'] + 1)
    ub.execute(latest)
    assert not ub.message_storage.messages


GUARDIAN = '0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A'


def _stubbed_bot(web3_lido_unit, sends: list[bool]) -> UnvetterBot:
    bot = UnvetterBot(web3_lido_unit)
    bot.prepare_transport_bus = Mock()
    bot.receive_unvet_messages = Mock(return_value=[{'stakingModuleId': 1}] * len(sends))
    bot._send_unvet_message = Mock(side_effect=sends)
    return bot


@pytest.mark.unit
def test_execute_reports_failure_when_a_send_fails(web3_lido_unit):
    bot = _stubbed_bot(web3_lido_unit, [True, False, True])

    assert bot.execute(Mock()) is False
    assert bot._send_unvet_message.call_count == 3


@pytest.mark.unit
def test_execute_reports_success_when_all_sends_succeed(web3_lido_unit):
    assert _stubbed_bot(web3_lido_unit, [True, True]).execute(Mock()) is True


@pytest.mark.unit
def test_execute_reports_success_when_there_is_nothing_to_send(web3_lido_unit):
    assert _stubbed_bot(web3_lido_unit, []).execute(Mock()) is True


@pytest.mark.unit
def test_actualize_filter_drops_messages_past_the_blockhash_window(web3_lido_unit):
    bot = UnvetterBot(web3_lido_unit)
    web3_lido_unit.eth.get_block = Mock(return_value={'number': 1_000})
    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1])
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=5)
    web3_lido_unit.lido.deposit_security_module.get_guardians = Mock(return_value=[GUARDIAN])

    message_filter = bot._get_message_actualize_filter()
    message = {'guardianAddress': GUARDIAN, 'stakingModuleId': 1, 'nonce': 5, 'blockNumber': 900}

    assert message_filter(message) is True
    assert message_filter({**message, 'blockNumber': 700}) is False
