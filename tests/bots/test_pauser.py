import logging
from unittest.mock import Mock

import pytest
import variables
from bots.pauser import PauserBot
from cryptography.verify_signature import compute_vs
from transport.msg_providers.onchain_transport import PauseV3Parser
from utils.bytes import from_hex_string_to_bytes

from tests.conftest import DSM_OWNER
from tests.fixtures import upgrade_staking_router_to_v2

# WARNING: These accounts, and their private keys, are publicly known.
COUNCIL_ADDRESS = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8'
COUNCIL_PK = '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d'


@pytest.fixture
def pause_bot(web3_lido_unit, block_data):
    web3_lido_unit.eth.get_block = Mock(return_value=block_data)
    variables.MESSAGE_TRANSPORTS = ''
    web3_lido_unit.lido.deposit_security_module.get_pause_intent_validity_period_blocks = Mock(return_value=10)
    web3_lido_unit.lido.deposit_security_module.get_guardians = Mock(return_value=[COUNCIL_ADDRESS])
    yield PauserBot(web3_lido_unit)


@pytest.fixture
def pause_message():
    yield {
        'blockHash': '0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c',
        'blockNumber': 10,
        'guardianAddress': COUNCIL_ADDRESS,
        'guardianIndex': 0,
        'stakingModuleId': 1,
        'signature': {
            '_vs': '0xd4933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537',
            'r': '0xbaa668505cd496caaf7117dd074338197200175057909ab73a04463656bdb0fa',
            'recoveryParam': 1,
            's': '0x54933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537',
            'v': 28,
        },
        'type': 'pause',
    }


@pytest.fixture
def add_account_to_guardian(web3_lido_integration, set_integration_account):
    web3_lido_integration.provider.make_request('anvil_impersonateAccount', [DSM_OWNER])
    web3_lido_integration.provider.make_request('anvil_setBalance', [DSM_OWNER, '0x500000000000000000000000'])
    quorum_size = web3_lido_integration.lido.deposit_security_module.get_guardian_quorum()

    # If guardian removal failed
    web3_lido_integration.lido.deposit_security_module.functions.addGuardian(COUNCIL_ADDRESS, quorum_size).transact(
        {'from': DSM_OWNER},
    )

    yield COUNCIL_ADDRESS


def get_pause_message(web3, module_id):
    latest = web3.eth.get_block('latest')

    prefix = web3.lido.deposit_security_module.get_pause_message_prefix()

    block_number = latest.number

    msg_hash = web3.solidity_keccak(['bytes32', 'uint256', 'uint256'], [prefix, block_number, module_id])
    signed = web3.eth.account._sign_hash(msg_hash, private_key=COUNCIL_PK)

    return {
        'blockHash': latest.hash.hex(),
        'blockNumber': latest.number,
        'guardianAddress': COUNCIL_ADDRESS,
        'stakingModuleId': module_id,
        'signature': {
            'r': '0x' + signed.r.to_bytes(32, 'big').hex(),
            's': '0x' + signed.s.to_bytes(32, 'big').hex(),
            'v': signed.v,
            '_vs': compute_vs(signed.v, '0x' + signed.s.to_bytes(32, 'big').hex()),
        },
        'type': 'pause',
    }


def get_pause_message_v3(web3):
    latest = web3.eth.get_block('latest')

    prefix = web3.lido.deposit_security_module.get_pause_message_prefix()

    block_number = latest.number

    msg_hash = web3.solidity_keccak(['bytes32', 'uint256'], [prefix, block_number])
    signed = web3.eth.account._sign_hash(msg_hash, private_key=COUNCIL_PK)

    return PauseV3Parser.build_message(
        block_number=block_number,
        guardian=COUNCIL_ADDRESS,
        version=b'0x1',
        r=signed.r.to_bytes(32, 'big'),
        vs=from_hex_string_to_bytes(compute_vs(signed.v, '0x' + signed.s.to_bytes(32, 'big').hex())),
    )


@pytest.mark.unit
def test_pause_bot_without_messages(pause_bot, block_data):
    pause_bot.message_storage.get_messages_and_actualize = Mock(return_value=[])
    pause_bot._send_pause_message = Mock()
    pause_bot.execute(block_data)
    pause_bot._send_pause_message.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    'block_range',
    [
        4,
        pytest.param(6, marks=pytest.mark.xfail(raises=AssertionError, strict=True)),
    ],
)
def test_pause_bot_outdate_messages(pause_bot, block_data, pause_message, block_range):
    pause_message['blockNumber'] = 5
    pause_bot.message_storage.messages = [pause_message]
    pause_bot.w3.lido.deposit_security_module.get_pause_intent_validity_period_blocks = Mock(return_value=block_range)
    pause_bot._sign_filter = Mock(return_value=lambda _: True)

    pause_bot._send_pause_message = Mock()
    pause_bot.execute(block_data)
    pause_bot._send_pause_message.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    'active_module',
    [
        False,
        pytest.param(True, marks=pytest.mark.xfail(raises=AssertionError, strict=True)),
    ],
)
def test_pause_bot_clean_messages(pause_bot, block_data, pause_message, active_module):
    pause_bot.message_storage.messages = [pause_message]
    pause_bot.w3.lido.staking_router.is_staking_module_active = Mock(return_value=active_module)

    pause_bot._sign_filter = Mock(return_value=lambda _: True)

    pause_bot.execute(block_data)
    assert len(pause_bot.message_storage.messages) == 0


@pytest.mark.unit
def test_pause_message_filtered_by_module_id(pause_bot, block_data, pause_message):
    new_message = pause_message.copy()
    new_message['stakingModuleId'] = 2

    pause_bot._sign_filter = Mock(return_value=lambda _: True)

    pause_bot.message_storage.messages = [pause_message, pause_message, new_message]
    pause_bot.w3.lido.staking_router.is_staking_module_active = lambda module_id: not module_id % 2

    pause_bot.execute(block_data)

    # Only module_id=1 messages filtered
    assert len(pause_bot.message_storage.messages) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration,module_id',
    [[{'block': 19628126}, 1], [{'block': 19628126}, 2]],
    indirect=['web3_provider_integration'],
)
def test_pauser_bot(web3_lido_integration, web3_provider_integration, add_account_to_guardian, module_id, caplog):
    caplog.set_level(logging.INFO)
    latest = web3_lido_integration.eth.get_block('latest')

    pm = get_pause_message(web3_lido_integration, module_id)

    pb = PauserBot(web3_lido_integration)
    pb._get_message_actualize_filter = Mock(return_value=lambda x: True)
    pb.execute(latest)

    web3_lido_integration.provider.make_request('anvil_mine', [1])

    # Check no pause
    assert web3_lido_integration.lido.staking_router.is_staking_module_active(module_id)

    # Add pause message
    pb.message_storage.messages = [pm]
    web3_lido_integration.lido.deposit_security_module.get_guardians = Mock(return_value=[COUNCIL_ADDRESS])
    pb.execute(latest)

    web3_lido_integration.provider.make_request('anvil_mine', [1])

    # Check there is pause message and module paused
    assert not web3_lido_integration.lido.staking_router.is_staking_module_active(module_id)
    assert len(pb.message_storage.messages) == 1

    pb.execute(latest)
    # Check pause message cleaned
    assert not pb.message_storage.messages

    pb.message_storage.messages = [get_pause_message_v3(web3_lido_integration)]
    pb.execute(latest)
    assert pb.message_storage.messages

    upgrade_staking_router_to_v2(web3_lido_integration)
    web3_lido_integration.lido.deposit_security_module.get_guardians = Mock(return_value=[COUNCIL_ADDRESS])
    # recreate signature
    pb.message_storage.messages = [get_pause_message_v3(web3_lido_integration)]
    pb.execute(latest)
    assert pb.message_storage.messages
    assert [
        msg
        for msg in caplog.messages
        if (
            "Build `pauseDeposits(19628132, ('0xafd5cffaea441e00ec6aaf081589ea70ee665c827047071b28153e4472ce48fa', "
            "'0x4c4ea8132ca88766d4beead65d47330b15e7921e7dc71de162fc2a971d8800b4'))` tx."
        )
        in msg
    ]

    pb.execute(latest)
    assert not pb.message_storage.messages
