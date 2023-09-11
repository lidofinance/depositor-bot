import logging
from unittest.mock import Mock

import pytest

import variables
from blockchain.web3_extentions.transaction import TransactionUtils


@pytest.mark.unit
def test_get_priority_fee(web3_lido_unit):
    tu = TransactionUtils(web3_lido_unit)
    tu.web3.eth.fee_history = Mock(return_value={'reward': [[50]]})

    assert tu._get_priority_fee(0, 10, 30) == 30
    assert tu._get_priority_fee(0, 10, 70) == 50
    assert tu._get_priority_fee(0, 60, 70) == 60


@pytest.mark.unit
def test_protector_no_account(web3_lido_unit, caplog):
    caplog.set_level(logging.INFO)

    tu = TransactionUtils(web3_lido_unit)
    variables.CREATE_TRANSACTIONS = False
    tu.send(None, False, 10)
    assert 'Account was not provided. Sending transaction skipped.' in caplog.messages[-1]


@pytest.mark.unit
def test_protector_create_tx(web3_lido_unit, set_integration_account, caplog):
    caplog.set_level(logging.INFO)

    tu = TransactionUtils(web3_lido_unit)
    variables.CREATE_TRANSACTIONS = False
    tu.send(None, False, 10)
    assert 'Dry mode activated. Sending transaction skipped.' in caplog.messages[-1]
