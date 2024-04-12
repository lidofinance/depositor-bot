import logging
from unittest.mock import Mock

import pytest

from bots.unvetter import UnvetterBot
from tests.fixtures import upgrade_staking_router_to_v2
from transport.msg_types.unvet import UnvetMessage


# WARNING: These accounts, and their private keys, are publicly known.
COUNCIL_ADDRESS = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8'
COUNCIL_PK = '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d'


def get_unvet_message(web3) -> UnvetMessage:
    latest = web3.eth.get_block('latest')
    block_number = latest.number

    prefix = web3.lido.deposit_security_module.get_unvet_message_prefix()
    nonce = web3.lido.staking_router.functions.getStakingModuleNonce(1).call()

    msg_hash = web3.solidity_keccak(
        ['bytes32', 'uint256', 'uint256', 'uint256[]', 'uint256[]'],
        [prefix, block_number, nonce, [1], [1]],
    )
    signed = web3.eth.account._sign_hash(msg_hash, private_key=COUNCIL_PK)

    return {
        "blockNumber": latest.number,
        "guardianAddress": COUNCIL_ADDRESS,
        "stakingModuleId": 1,
        "nonce": nonce,
        "operatorIds": [1],
        "vettedKeysByOperator": [1],
        "signature": {
            "r": '0x' + signed.r.to_bytes(32, 'big').hex(),
            "s": '0x' + signed.s.to_bytes(32, 'big').hex(),
            "v": signed.v,
        },
        "type": "unvet"
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    "web3_provider_integration",
    [19628126],
    indirect=["web3_provider_integration"],
)
def test_unvetter(web3_provider_integration, web3_lido_integration, caplog):
    latest = web3_lido_integration.eth.get_block('latest')

    ub = UnvetterBot(web3_lido_integration)
    ub.execute(latest)

    assert not ub.fully_initialized

    upgrade_staking_router_to_v2(web3_lido_integration)

    ub.execute(latest)
    assert ub.fully_initialized

    web3_lido_integration.lido.deposit_security_module.get_guardians = Mock(return_value=[COUNCIL_ADDRESS])
    ub.message_storage.messages = [get_unvet_message(web3_lido_integration)]

    caplog.set_level(logging.INFO)

    ub.execute(latest)

    assert [
        msg for msg in caplog.messages
        if 'Build `unvetSigningKeys(' in msg
    ]
    assert ub.message_storage.messages

    web3_lido_integration.lido.staking_router.get_staking_module_nonce = Mock(return_value=ub.message_storage.messages[0]['nonce'] + 1)
    ub.execute(latest)
    assert not ub.message_storage.messages
