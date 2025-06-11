import logging
from unittest.mock import Mock

import pytest
import variables
from blockchain.typings import Web3
from bots.unvetter import UnvetterBot
from cryptography.verify_signature import compute_vs
from transport.msg_providers.onchain_transport import UnvetParser
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

    unvet_message = UnvetParser.build_message(
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


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [
        {
            'block': 21318213,
        }
    ],
    indirect=['web3_provider_integration'],
)
def test_unvetter(web3_provider_integration, web3_lido_integration, caplog):
    # explicitly set v2 address
    variables.LIDO_LOCATOR = Web3.to_checksum_address('0x3ABc4764f0237923d52056CFba7E9AEBf87113D3')

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
