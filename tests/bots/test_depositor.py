import logging
from unittest.mock import Mock

import pytest

import variables
from bots.depositor import DepositorBot
from tests.conftest import DSM_OWNER

COUNCIL_ADDRESS_1 = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8'
COUNCIL_PK_1 = '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d'

COUNCIL_ADDRESS_2 = '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC'
COUNCIL_PK_2 = '0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a'


@pytest.fixture
def depositor_bot(web3_lido_unit, block_data):
    variables.MESSAGE_TRANSPORTS = ''
    variables.DEPOSIT_MODULES_WHITELIST = [1, 2]
    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1, 2])
    web3_lido_unit.eth.get_block = Mock(return_value=block_data)
    yield DepositorBot(web3_lido_unit)


@pytest.fixture
def deposit_message():
    yield {
        "type": "deposit",
        "depositRoot": "0x64dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b",
        "nonce": 12,
        "blockNumber": 10,
        "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
        "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        "guardianIndex": 8,
        "stakingModuleId": 1,
        "signature": {
            "r": "0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116",
            "s": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "_vs": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "recoveryParam": 0,
            "v": 27
        },
        "app": {
            "version": "1.0.3",
            "name": "lido-council-daemon"
        }
    }


@pytest.mark.unit
def test_depositor_one_module_deposited(depositor_bot, block_data):
    modules = list(range(10))

    depositor_bot.w3.lido.deposit_security_module.get_max_deposits = Mock(return_value=100)
    depositor_bot.w3.lido.lido.get_depositable_ether = Mock(return_value=10 * 32 * 10 ** 18)
    depositor_bot.w3.lido.staking_router.get_staking_module_ids = Mock(return_value=modules)
    depositor_bot.w3.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=0)

    depositor_bot._deposit_to_module = Mock(return_value=True)
    depositor_bot.execute(block_data)

    assert depositor_bot._deposit_to_module.call_count == 1


@pytest.mark.unit
def test_check_balance_dry(depositor_bot, caplog):
    caplog.set_level(logging.INFO)
    depositor_bot._check_balance()
    assert 'No account provided. Dry mode.' in caplog.messages[-1]


@pytest.mark.unit
def test_check_balance(depositor_bot, caplog, set_account):
    caplog.set_level(logging.INFO)

    depositor_bot.w3.eth.get_balance = Mock(return_value=10*10**18)
    depositor_bot._check_balance()
    assert 'Check account balance' in caplog.messages[-1]


@pytest.mark.unit
def test_depositor_check_module_status(depositor_bot):
    depositor_bot.w3.lido.staking_router.is_staking_module_active = Mock(return_value=True)
    assert depositor_bot._check_module_status(1)

    depositor_bot.w3.lido.staking_router.is_staking_module_active = Mock(return_value=False)
    assert not depositor_bot._check_module_status(1)


@pytest.mark.unit
@pytest.mark.parametrize(
    "is_depositable,quorum,is_gas_price_ok,is_deposited_keys_amount_ok",
    [
        pytest.param(True, True, True, True, marks=pytest.mark.xfail),
        (False, True, True, True),
        (True, False, True, True),
        (True, True, False, True),
        (True, True, True, False),
    ],
)
def test_depositor_deposit_to_module(depositor_bot, is_depositable, quorum, is_gas_price_ok, is_deposited_keys_amount_ok):
    depositor_bot._check_module_status = Mock(return_value=is_depositable)
    depositor_bot._get_quorum = Mock(return_value=quorum)

    strategy = Mock()
    strategy.is_gas_price_ok = Mock(return_value=is_gas_price_ok)
    strategy.is_deposited_keys_amount_ok = Mock(return_value=is_deposited_keys_amount_ok)

    depositor_bot._get_module_strategy = Mock(return_value=strategy)
    depositor_bot._build_and_send_deposit_tx = Mock(return_value=True)

    assert not depositor_bot._deposit_to_module(1)


@pytest.fixture
def setup_deposit_message(depositor_bot, block_data):
    depositor_bot.w3.eth.get_block = Mock(return_value=block_data)
    depositor_bot.w3.lido.deposit_contract.get_deposit_root = Mock(
        return_value=b'd\xdc\xf7\nz\xd7\xfck\x1aU\xdbk\x08\xb8n\x9d\x80sbY\x91o\xca\xef\x98\xf4q\x0f\x0b\xach{'
    )
    depositor_bot.w3.lido.staking_router.get_staking_module_nonce = Mock(return_value=12)
    depositor_bot.w3.lido.deposit_security_module.get_guardians = Mock(return_value=['0x43464Fe06c18848a2E2e913194D64c1970f4326a'])


@pytest.mark.unit
def test_depositor_message_actualizer(setup_deposit_message, depositor_bot, deposit_message, block_data):
    message_filter = depositor_bot._get_message_actualize_filter(1)
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_not_guardian(setup_deposit_message, depositor_bot, deposit_message, block_data):
    depositor_bot.w3.lido.deposit_security_module.get_guardians = Mock(return_value=['0x13464Fe06c18848a2E2e913194D64c1970f4326a'])
    message_filter = depositor_bot._get_message_actualize_filter(1)
    assert not list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_outdated(setup_deposit_message, depositor_bot, deposit_message, block_data):
    deposit_message['blockNumber'] = block_data['number'] - 250
    message_filter = depositor_bot._get_message_actualize_filter(1)
    assert not list(filter(message_filter, [deposit_message]))

    deposit_message['blockNumber'] = block_data['number'] - 150
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_nonce(setup_deposit_message, depositor_bot, deposit_message, block_data):
    deposit_message['nonce'] += 10
    message_filter = depositor_bot._get_message_actualize_filter(1)
    assert not list(filter(message_filter, [deposit_message]))

    deposit_message['blockNumber'] = block_data['number'] + 100
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_depositor_message_actualizer_root(setup_deposit_message, depositor_bot, deposit_message, block_data):
    deposit_message['depositRoot'] += '0x55dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b'
    message_filter = depositor_bot._get_message_actualize_filter(1)
    assert not list(filter(message_filter, [deposit_message]))

    deposit_message['blockNumber'] = block_data['number'] + 100
    assert list(filter(message_filter, [deposit_message]))


@pytest.mark.unit
def test_prepare_signs_for_deposit(deposit_message, depositor_bot):
    second_council = {
        "guardianAddress": "0x13464Fe06c18848a2E2e913194D64c1970f4326a",
        "signature": {
            "r": "0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116",
            "s": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "_vs": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "recoveryParam": 0,
            "v": 27
        },
    }

    expected = (('0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116', '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0'), ('0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116', '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0'))

    signs = depositor_bot._prepare_signs_for_deposit([second_council, deposit_message])
    assert signs == expected

    signs = depositor_bot._prepare_signs_for_deposit([deposit_message, second_council])
    assert signs == expected


@pytest.mark.unit
def test_send_deposit_tx(depositor_bot):
    depositor_bot.w3.transaction.check = Mock(return_value=False)
    params = [
        1, b'', b'', 1, 1, b'', tuple(),
    ]
    assert not depositor_bot._send_deposit_tx(*params)

    depositor_bot.w3.transaction.check = Mock(return_value=True)
    depositor_bot.w3.transaction.send = Mock(return_value=True)
    assert depositor_bot._send_deposit_tx(*params)
    assert depositor_bot._flashbots_works

    depositor_bot.w3.transaction.send = Mock(return_value=False)
    assert not depositor_bot._send_deposit_tx(*params)
    assert not depositor_bot._flashbots_works

    assert not depositor_bot._send_deposit_tx(*params)
    assert depositor_bot._flashbots_works


@pytest.mark.unit
def test_get_quorum(depositor_bot, setup_deposit_message):
    deposit_messages = [
        {
            "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
            "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        },
        {
            "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
            "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        },
        {
            "blockHash": "0x232e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
            "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
        },
        {
            "blockHash": "0x232e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
            "guardianAddress": "0x33464Fe06c18848a2E2e913194D64c1970f4326a",
        }
    ]

    depositor_bot.w3.lido.deposit_security_module.get_guardian_quorum = Mock(return_value=2)
    depositor_bot.message_storage.get_messages = Mock(return_value=deposit_messages[:2])
    assert not depositor_bot._get_quorum(1)

    depositor_bot.message_storage.get_messages = Mock(return_value=deposit_messages[:4])
    quorum = depositor_bot._get_quorum(1)
    assert quorum
    assert deposit_messages[2] in quorum
    assert deposit_messages[3] in quorum


def get_deposit_message(web3, account_address, pk, module_id):
    latest = web3.eth.get_block('latest')

    prefix = web3.lido.deposit_security_module.get_attest_message_prefix()
    block_number = latest.number
    deposit_root = '0x' + web3.lido.deposit_contract.get_deposit_root().hex()
    staking_module_id = int(1)
    nonce = web3.lido.staking_router.get_staking_module_nonce(module_id)

    # | ATTEST_MESSAGE_PREFIX | blockNumber | blockHash | depositRoot | stakingModuleId | nonce |

    msg_hash = web3.solidityKeccak(
        ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
        [prefix, block_number, latest.hash.hex(), deposit_root, staking_module_id, nonce],
    )
    signed = web3.eth.account.signHash(msg_hash, private_key=pk)

    msg = {
        "type": "deposit",
        "depositRoot": deposit_root,
        "nonce": nonce,
        "blockNumber": latest.number,
        "blockHash": latest.hash.hex(),
        "guardianAddress": account_address,
        "guardianIndex": 8,
        "stakingModuleId": staking_module_id,
        "signature": {
            "r": signed.r.to_bytes(32, 'big').hex(),
            "s": signed.s.to_bytes(32, 'big').hex(),
            "v": signed.v,
        },
    }

    return msg


@pytest.fixture
def add_accounts_to_guardian(web3_lido_integration, set_integration_account):
    web3_lido_integration.provider.make_request('hardhat_impersonateAccount', [DSM_OWNER])
    quorum_size = web3_lido_integration.lido.deposit_security_module.get_guardian_quorum()

    try:
        # If guardian removal failed
        web3_lido_integration.lido.deposit_security_module.functions.addGuardian(COUNCIL_ADDRESS_1, 2).transact({'from': DSM_OWNER})
        web3_lido_integration.lido.deposit_security_module.functions.addGuardian(COUNCIL_ADDRESS_2, 2).transact({'from': DSM_OWNER})
    except:
        pass

    yield web3_lido_integration

    web3_lido_integration.lido.deposit_security_module.functions.removeGuardian(COUNCIL_ADDRESS_1, quorum_size).transact({'from': DSM_OWNER})
    web3_lido_integration.lido.deposit_security_module.functions.removeGuardian(COUNCIL_ADDRESS_2, quorum_size).transact({'from': DSM_OWNER})


@pytest.mark.integration
def test_depositor_bot(web3_lido_integration, add_accounts_to_guardian, caplog):
    max_deposits = web3_lido_integration.lido.deposit_security_module.functions.getMaxDeposits().call()
    web3_lido_integration.lido.deposit_security_module.functions.setMaxDeposits(2).transact({'from': DSM_OWNER})

    latest = web3_lido_integration.eth.get_block('latest')

    module_id = 1

    old_module_nonce = web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id)

    deposit_message_1 = get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_1, COUNCIL_PK_1, module_id)
    deposit_message_2 = get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_2, COUNCIL_PK_2, module_id)
    deposit_message_3 = get_deposit_message(web3_lido_integration, COUNCIL_ADDRESS_2, COUNCIL_PK_2, module_id)

    db = DepositorBot(web3_lido_integration)
    db.message_storage.messages = [deposit_message_2, deposit_message_3]
    db.execute(latest)

    assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce

    web3_lido_integration.eth.send_transaction({
        "from": web3_lido_integration.eth.accounts[0],
        "to": web3_lido_integration.lido.lido.address,
        "value": 2000 * 10**18
    })

    db.message_storage.messages = [deposit_message_1, deposit_message_2, deposit_message_3]
    db._get_module_strategy = Mock(return_value=Mock(return_value=True))
    assert db.execute(latest)
    # assert web3_lido_integration.lido.staking_router.get_staking_module_nonce(module_id) == old_module_nonce + 1
    web3_lido_integration.lido.deposit_security_module.functions.setMaxDeposits(max_deposits).transact({'from': DSM_OWNER})
