from unittest.mock import Mock

import pytest
import requests
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
    web3.attach_modules({
        'transaction': TransactionUtils,
    })

    yield web3


# -- Integration fixtures --
@pytest.fixture
def web3_provider_integration():
    chronix_url = 'http://0.0.0.0:8080/'
    hardhat_path = 'v1/env/hardhat/'

    response = requests.put(
        chronix_url + hardhat_path,
        json={
            'chainId': 1,
            'fork': variables.WEB3_RPC_ENDPOINTS[0],
            'mining': {
                'auto': True,
                'interval': 12000
            }
        },
        headers={
            'Content-Type': 'application/json'
        },
    )

    port = response.json()['data']['port']

    yield Web3(FallbackProvider([f'http://0.0.0.0:{port}/']))

    requests.delete(chronix_url + hardhat_path, json={'port': port})


@pytest.fixture
def web3_lido_integration(web3_provider_integration):
    web3_provider_integration.attach_modules({
        'lido': LidoContracts,
        'transaction': TransactionUtils,
    })
    yield web3_provider_integration
