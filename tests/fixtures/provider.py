from unittest.mock import Mock

import pytest
from web3 import Web3
from web3_multi_provider import FallbackProvider

import variables
from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.transaction import TransactionUtils


# -- Unit fixtures --
@pytest.fixture
def web3_lido_unit():
    web3 = Web3()
    web3.lido = Mock()
    web3.transaction = Mock()
    yield web3


# -- Integration fixtures --
@pytest.fixture
def web3_provider_integration():
    yield Web3(FallbackProvider(variables.WEB3_RPC_ENDPOINTS))


@pytest.fixture
def web3_lido_integration(web3_provider_integration):
    web3_provider_integration.attach_modules({
        'lido': LidoContracts,
        'transaction': TransactionUtils,
    })
    yield web3_provider_integration
