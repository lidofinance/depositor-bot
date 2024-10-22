import os
from unittest.mock import Mock

import pytest
import variables
from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.transaction import TransactionUtils
from web3 import HTTPProvider, Web3

from tests.fork import anvil_fork


# -- Unit fixtures --
@pytest.fixture
def web3_lido_unit() -> Web3:
    web3 = Web3()
    web3.lido = Mock()
    web3.attach_modules(
        {
            'transaction': TransactionUtils,
        }
    )

    yield web3


# -- Integration fixtures --
@pytest.fixture
def web3_provider_integration(request) -> Web3:
    params = getattr(request, 'param', {})
    rpc_endpoint = params.get('endpoint', variables.WEB3_RPC_ENDPOINTS[0])
    block_num = params.get('block', None)
    anvil_path = os.getenv('ANVIL_PATH', '')

    with anvil_fork(anvil_path, rpc_endpoint, block_num):
        web3 = Web3(HTTPProvider('http://127.0.0.1:8545', request_kwargs={'timeout': 3600}))
        assert web3.is_connected(), 'Failed to connect to the Web3 provider.'
        yield web3


@pytest.fixture
def web3_transaction_integration(web3_provider_integration: Web3) -> Web3:
    web3_provider_integration.attach_modules(
        {
            'transaction': TransactionUtils,
        }
    )
    yield web3_provider_integration


@pytest.fixture
def web3_lido_integration(web3_transaction_integration: Web3) -> Web3:
    web3_transaction_integration.attach_modules(
        {
            'lido': LidoContracts,
        }
    )
    yield web3_transaction_integration
