import logging
from unittest.mock import Mock

import pytest
import variables
from blockchain.typings import Web3
from blockchain.web3_extentions.direct_deposit import is_mellow_depositable
from blockchain.web3_extentions.transaction import TransactionUtils
from web3.exceptions import ContractLogicError


@pytest.mark.unit
def test_is_mellow_depositable(web3_lido_unit):
    variables.MELLOW_CONTRACT_ADDRESS = None
    assert not is_mellow_depositable(web3_lido_unit, 1)

    variables.MELLOW_CONTRACT_ADDRESS = '0x1'
    web3_lido_unit.lido.simple_dvt_staking_strategy.staking_module_contract.get_staking_module_id = Mock(return_value=1)
    assert not is_mellow_depositable(web3_lido_unit, 2)

    web3_lido_unit.lido.simple_dvt_staking_strategy.vault_balance = Mock(return_value=Web3.to_wei(0.5, 'ether'))
    assert not is_mellow_depositable(web3_lido_unit, 1)

    web3_lido_unit.lido.simple_dvt_staking_strategy.vault_balance = Mock(return_value=Web3.to_wei(1.4, 'ether'))
    assert is_mellow_depositable(web3_lido_unit, 1)
