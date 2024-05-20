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
def web3_lido_unit():
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
def web3_provider_integration(request):
	block_num = getattr(request, 'param', None)

	with anvil_fork(
		os.getenv('ANVIL_PATH', ''),
		variables.WEB3_RPC_ENDPOINTS[0],
		block_num,
	):
		w3 = Web3(HTTPProvider('http://127.0.0.1:8545', request_kwargs={'timeout': 3600}))
		yield w3


@pytest.fixture
def web3_lido_integration(web3_provider_integration):
	web3_provider_integration.attach_modules(
		{
			'lido': LidoContracts,
			'transaction': TransactionUtils,
		}
	)
	yield web3_provider_integration
