from unittest.mock import Mock

import pytest
import variables
from transport.msg_types.deposit import DepositMessage

MODULE_ID = 1337


@pytest.fixture
def cmds(web3_lido_unit):
    yield CuratedModuleDepositStrategy(web3_lido_unit, module_id=MODULE_ID)


@pytest.mark.unit
def test_is_deposited_keys_amount_ok(cmds):
    cmds.get_possible_deposits_amount = Mock(return_value=100)

    cmds.calculate_recommended_gas_based_on_deposit_amount = Mock(return_value=30)
    cmds.get_pending_base_fee = Mock(return_value=20)

    assert cmds.deposited_keys_amount()

    cmds.get_pending_base_fee = Mock(return_value=50)
    assert not cmds.deposited_keys_amount()


@pytest.mark.unit
def test_get_possible_deposits_amount(cmds):
    depositable_eth = 100
    possible_deposits = depositable_eth // 32

    cmds.w3.lido.lido.get_depositable_ether = Mock(return_value=depositable_eth)
    cmds.w3.lido.staking_router.get_staking_module_max_deposits_count = Mock(return_value=possible_deposits)

    assert cmds.get_possible_deposits_amount() == possible_deposits
    cmds.w3.lido.staking_router.get_staking_module_max_deposits_count.assert_called_once_with(
        MODULE_ID,
        depositable_eth,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    'deposits,expected_range',
    [(1, (0, 20)), (5, (20, 100)), (10, (50, 1000)), (100, (1000, 1000000))],
)
def test_calculate_recommended_gas_based_on_deposit_amount(cmds, deposits, expected_range):
    assert expected_range[0] * 10 ** 9 <= cmds.calculate_recommended_gas_based_on_deposit_amount(deposits) <= expected_range[1] * 10 ** 9


@pytest.mark.unit
def test_get_recommended_gas_fee(cmds):
    cmds._fetch_gas_fee_history = Mock(return_value=list(range(11)))
    variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1 = 1
    variables.GAS_FEE_PERCENTILE_1 = 50

    assert cmds._get_recommended_gas_fee() == 5

    variables.GAS_FEE_PERCENTILE_1 = 30
    assert cmds._get_recommended_gas_fee() == 3


@pytest.mark.unit
def test_is_gas_price_ok(cmds):
    cmds.get_pending_base_fee = Mock(return_value=10)
    cmds._get_recommended_gas_fee = Mock(return_value=20)
    variables.MAX_GAS_FEE = 300

    cmds.w3.lido.lido.get_depositable_ether = Mock(return_value=100)
    variables.MAX_BUFFERED_ETHERS = 200
    assert cmds.is_gas_price_ok()

    cmds._get_recommended_gas_fee = Mock(return_value=5)
    assert not cmds.is_gas_price_ok()

    cmds.w3.lido.lido.get_depositable_ether = Mock(return_value=300)
    assert cmds.is_gas_price_ok()

    cmds.get_pending_base_fee = Mock(return_value=400)
    assert not cmds.is_gas_price_ok()


@pytest.fixture()
def cmds_integration(web3_lido_integration):
    yield CuratedModuleDepositStrategy(web3_lido_integration, module_id=MODULE_ID)


@pytest.mark.integration
def test_get_pending_base_fee(cmds_integration):
    pending_gas = cmds_integration.get_pending_base_fee()
    assert 1 <= pending_gas <= 1000 * 10 ** 9


@pytest.mark.integration
def test_fetch_gas_fee_history(cmds_integration):
    history = cmds_integration._fetch_gas_fee_history(1)
    assert isinstance(history, list)
    assert len(history) == 1 * 24 * 60 * 60 / 12

    cmds_integration.w3.eth.fee_history = Mock()
    cmds_integration._fetch_gas_fee_history(1)
    assert len(history) == 1 * 24 * 60 * 60 / 12
    cmds_integration.w3.eth.fee_history.assert_not_called()


@pytest.mark.unit
def test_send_deposit_tx(cmds):
    cmds.w3.transaction.check = Mock(return_value=False)
    messages = [DepositMessage(
        type='deposit',
        depositRoot='',
        nonce=1,
        blockNumber=1,
        blockHash='',
        guardianAddress='0x43464Fe06c18848a2E2e913194D64c1970f4326a',
        stakingModuleId=1,
        signature={
            'r': '0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116',
            's': '0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0',
            'v': 27,
        },
        app={'version': '1.0.3', 'name': 'lido-council-daemon'},
    )]
    cmds._prepare_signs_for_deposit = Mock(return_value=tuple())
    cmds.is_gas_price_ok = Mock(return_value=True)
    cmds.deposited_keys_amount = Mock(return_value=True)
    assert not cmds.prepare_and_send(messages, False)

    cmds.w3.transaction.check = Mock(return_value=True)
    cmds.w3.transaction.send = Mock(return_value=True)
    assert cmds.prepare_and_send(messages, False)
    cmds.w3.transaction.send = Mock(return_value=False)
    assert not cmds.prepare_and_send(messages, False)
