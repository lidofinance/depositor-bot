import logging
from unittest.mock import Mock

import pytest

from bots.unvetter import UnvetterBot, _payload_key
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
    web3_lido_integration.lido.get_guardian_delegates = Mock(return_value={COUNCIL_ADDRESS: COUNCIL_ADDRESS})
    ub.message_storage.messages = [get_unvet_message(web3_lido_integration)]

    caplog.set_level(logging.INFO)

    ub.execute(latest)

    assert [msg for msg in caplog.messages if 'Build `unvetSigningKeys(' in msg]
    assert ub.message_storage.messages

    web3_lido_integration.lido.staking_router.get_staking_module_nonce = Mock(return_value=ub.message_storage.messages[0]['nonce'] + 1)
    ub.execute(latest)
    assert not ub.message_storage.messages


GUARDIAN = '0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A'
DELEGATE = '0x5fd0dDbC3351d009eb3f88DE7Cd081a614C519F1'
REVOKED_DELEGATE = '0x43464Fe06c18848a2E2e913194D64c1970f4326a'
OTHER_GUARDIAN = '0x1111111111111111111111111111111111111111'


def _unvet_message(nonce: int = 5, module_id: int = 1) -> dict:
    return {
        'type': 'unvet',
        'blockNumber': 1,
        'blockHash': '0x' + '22' * 32,
        'guardianAddress': GUARDIAN,
        'guardianDelegate': DELEGATE,
        'stakingModuleId': module_id,
        'nonce': nonce,
        'operatorIds': '0x0000000000000001',
        'vettedKeysByOperator': '0x00000002',
        'signature': {'r': '0x' + '11' * 32, '_vs': '0x' + '22' * 32},
    }


@pytest.mark.unit
def test_storage_is_actualized_once_per_cycle(web3_lido_unit):
    bot = UnvetterBot(web3_lido_unit)
    bot.prepare_transport_bus = Mock()
    bot.message_storage = Mock()
    bot.receive_unvet_messages = Mock(return_value=[_unvet_message() for _ in range(20)])
    web3_lido_unit.lido.deposit_security_module.get_max_operators_per_unvetting = Mock(return_value=100)
    web3_lido_unit.lido.guardian_delegation_active = Mock(return_value=False)
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=6)
    web3_lido_unit.transaction = Mock()
    web3_lido_unit.transaction.check = Mock(return_value=False)

    bot.execute(Mock())

    assert bot.message_storage.get_messages_and_actualize.call_count == 1


@pytest.mark.unit
def test_outdated_messages_are_evicted_by_nonce(web3_lido_unit):
    bot = UnvetterBot(web3_lido_unit)
    bot.message_storage = Mock()
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=6)

    bot._clear_outdated_messages({1})
    (is_relevant,) = bot.message_storage.get_messages_and_actualize.call_args.args

    assert is_relevant(_unvet_message(nonce=6)) is True
    assert is_relevant(_unvet_message(nonce=5)) is False
    assert is_relevant(_unvet_message(nonce=0, module_id=2)) is True  # module untouched this cycle


@pytest.mark.unit
def test_actualize_filter_drops_revoked_delegate(web3_lido_unit):
    bot = UnvetterBot(web3_lido_unit)
    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1])
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=5)
    web3_lido_unit.lido.get_guardian_delegates = Mock(return_value={DELEGATE: GUARDIAN})

    message_filter = bot._get_message_actualize_filter()

    assert message_filter(_unvet_message()) is True
    assert message_filter({**_unvet_message(), 'guardianDelegate': REVOKED_DELEGATE}) is False


@pytest.mark.unit
def test_delivered_message_is_evicted_without_a_nonce_change(web3_lido_unit):
    """A module that treats the payload as a no-op accepts it without advancing its nonce, so nonce
    alone would replay the same transaction until the message ages out."""
    bot = UnvetterBot(web3_lido_unit)
    bot.message_storage = Mock()
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=5)
    delivered = _unvet_message(nonce=5)

    bot._delivered = {_payload_key(delivered)}

    bot._clear_outdated_messages({1})
    (is_relevant,) = bot.message_storage.get_messages_and_actualize.call_args.args

    assert is_relevant(delivered) is False
    # Another guardian's copy of the same payload is consumed too.
    assert (
        is_relevant({**delivered, 'guardianAddress': OTHER_GUARDIAN, 'signature': {'r': '0x' + '99' * 32, '_vs': '0x' + '88' * 32}})
        is False
    )
    assert is_relevant({**delivered, 'vettedKeysByOperator': '0x00000001'}) is True


@pytest.mark.unit
def test_payload_is_sent_once_per_cycle(web3_lido_unit):
    """Copies of one payload signed by different guardians must not each become a transaction."""
    bot = UnvetterBot(web3_lido_unit)
    bot.prepare_transport_bus = Mock()
    bot.message_storage = Mock()
    message = _unvet_message(nonce=5)
    copy = {**message, 'guardianAddress': OTHER_GUARDIAN, 'signature': {'r': '0x' + '99' * 32, '_vs': '0x' + '88' * 32}}
    bot.receive_unvet_messages = Mock(return_value=[message, copy])
    web3_lido_unit.lido.deposit_security_module.get_max_operators_per_unvetting = Mock(return_value=100)
    web3_lido_unit.lido.guardian_delegation_active = Mock(return_value=False)
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=5)
    web3_lido_unit.transaction = Mock()
    web3_lido_unit.transaction.check = Mock(return_value=True)
    web3_lido_unit.transaction.send = Mock(return_value=True)
    web3_lido_unit.transaction.broadcasting_enabled = Mock(return_value=True)

    bot.execute(Mock())

    assert web3_lido_unit.transaction.send.call_count == 1


@pytest.mark.unit
def test_message_is_kept_when_transaction_fails(web3_lido_unit):
    """Only a transaction that succeeded on-chain counts as delivered; otherwise the message is retried."""
    bot = UnvetterBot(web3_lido_unit)
    bot.prepare_transport_bus = Mock()
    bot.message_storage = Mock()
    message = _unvet_message(nonce=5)
    bot.receive_unvet_messages = Mock(return_value=[message])
    web3_lido_unit.lido.deposit_security_module.get_max_operators_per_unvetting = Mock(return_value=100)
    web3_lido_unit.lido.guardian_delegation_active = Mock(return_value=False)
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=5)
    web3_lido_unit.transaction = Mock()
    web3_lido_unit.transaction.check = Mock(return_value=True)
    web3_lido_unit.transaction.send = Mock(return_value=False)

    bot.execute(Mock())
    (is_relevant,) = bot.message_storage.get_messages_and_actualize.call_args.args

    assert is_relevant(message) is True


def _sending_bot(web3_lido_unit, messages: list, nonce: int = 5) -> UnvetterBot:
    bot = UnvetterBot(web3_lido_unit)
    bot.prepare_transport_bus = Mock()
    bot.message_storage = Mock()
    bot.receive_unvet_messages = Mock(return_value=messages)
    web3_lido_unit.lido.deposit_security_module.get_max_operators_per_unvetting = Mock(return_value=100)
    web3_lido_unit.lido.guardian_delegation_active = Mock(return_value=False)
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=nonce)
    web3_lido_unit.transaction = Mock()
    web3_lido_unit.transaction.check = Mock(return_value=True)
    web3_lido_unit.transaction.send = Mock(return_value=True)
    web3_lido_unit.transaction.broadcasting_enabled = Mock(return_value=True)
    return bot


@pytest.mark.unit
def test_late_copy_of_delivered_payload_is_not_resent(web3_lido_unit):
    """A copy arriving after the cycle that delivered its payload must be dropped, not sent again."""
    delivered = _unvet_message(nonce=5)
    bot = _sending_bot(web3_lido_unit, [delivered])
    bot.execute(Mock())

    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1])
    web3_lido_unit.lido.get_guardian_delegates = Mock(return_value={DELEGATE: GUARDIAN})
    late_copy = {**delivered, 'signature': {'r': '0x' + '99' * 32, '_vs': '0x' + '88' * 32}}

    assert bot._get_message_actualize_filter()(late_copy) is False


@pytest.mark.unit
def test_delivered_payloads_are_pruned_once_nonce_moves(web3_lido_unit):
    bot = _sending_bot(web3_lido_unit, [_unvet_message(nonce=5)])
    bot.execute(Mock())
    assert bot._delivered

    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1])
    web3_lido_unit.lido.staking_router.get_staking_module_nonce = Mock(return_value=6)
    web3_lido_unit.lido.get_guardian_delegates = Mock(return_value={DELEGATE: GUARDIAN})
    bot._get_message_actualize_filter()

    assert not bot._delivered


@pytest.mark.unit
def test_message_is_kept_when_nothing_is_broadcast(web3_lido_unit):
    """Dry run or no account: send() reports success without reaching the chain."""
    message = _unvet_message(nonce=5)
    bot = _sending_bot(web3_lido_unit, [message])
    web3_lido_unit.transaction.broadcasting_enabled = Mock(return_value=False)

    bot.execute(Mock())
    (is_relevant,) = bot.message_storage.get_messages_and_actualize.call_args.args

    assert is_relevant(message) is True
    assert not bot._delivered


@pytest.mark.unit
def test_delivered_payload_survives_a_failure_later_in_the_cycle(web3_lido_unit):
    first = _unvet_message(nonce=5)
    second = {**_unvet_message(nonce=5), 'vettedKeysByOperator': '0x00000001'}
    bot = _sending_bot(web3_lido_unit, [first, second])
    web3_lido_unit.transaction.send = Mock(side_effect=[True, RuntimeError('rpc down')])

    with pytest.raises(RuntimeError):
        bot.execute(Mock())

    assert bot._delivered == {_payload_key(first)}
