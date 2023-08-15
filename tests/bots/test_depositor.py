import logging
from unittest.mock import Mock

import pytest

import variables
from bots.depositor import DepositorBot


@pytest.fixture
def depositor_bot(web3_lido_unit, block_data):
    variables.MESSAGE_TRANSPORTS = ''
    web3_lido_unit.lido.staking_router.get_staking_module_ids = Mock(return_value=[1, 2])
    web3_lido_unit.eth.get_block = Mock(return_value=block_data)
    yield DepositorBot(web3_lido_unit)


@pytest.fixture
def deposit_message():
    yield {
        "type": "deposit",
        "depositRoot": "0x4eff65af4dac60f23b625a5d9c80f9cc36b0754cd1db072cd47bd6d053e2f94e",
        "nonce": 1,
        "blockNumber": 13726495,
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
def test_depositor_check_all_modules(depositor_bot, block_data):
    depositor_bot._deposit_to_module = Mock(return_value=False)
    depositor_bot.execute(block_data)

    assert depositor_bot._deposit_to_module.call_count == 2


@pytest.mark.unit
def test_depositor_one_module_deposited(depositor_bot, block_data):
    depositor_bot._deposit_to_module = Mock(return_value=True)
    depositor_bot.execute(block_data)

    depositor_bot._deposit_to_module.assert_called_once()


@pytest.mark.unit
def test_check_balance_dry(depositor_bot, caplog):
    caplog.set_level(logging.INFO)
    depositor_bot._check_balance()
    assert 'No account provided. Dry mode.' in caplog.messages[-1]


@pytest.mark.unit
def test_check_balance(depositor_bot, caplog, set_account):
    caplog.set_level(logging.INFO)

    depositor_bot.w3.eth.get_balance = Mock(return_value=50)
    depositor_bot._check_balance()
    assert 'Small account balance on address ' in caplog.messages[-1]

    depositor_bot.w3.eth.get_balance = Mock(return_value=10*10**18)
    depositor_bot._check_balance()
    assert 'Check account balance' in caplog.messages[-1]


@pytest.mark.unit
@pytest.mark.parametrize(
    "active,paused,expected",
    [
        (True, True, False),
        (True, False, True),
        (False, True, False),
        (False, False, False),
    ],
)
def test_depositor_check_module_status(depositor_bot, active, paused, expected):
    depositor_bot.w3.lido.staking_router.is_staking_module_active = Mock(return_value=active)
    depositor_bot.w3.lido.staking_router.is_staking_module_deposits_paused = Mock(return_value=paused)
    assert depositor_bot._check_module_status(1) == expected


# @pytest.mark.unit
# def test_depositor_deposit_to_module(depositor_bot):
#     depositor_bot._deposit_to_module(module_id=1)
