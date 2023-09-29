from unittest.mock import Mock
from urllib.parse import urlparse

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


CHRONIX_URL = 'http://0.0.0.0:8080/'


# -- Integration fixtures --
@pytest.fixture(scope="module")
def web3_provider_integration():
    hardhat_path = 'v1/env/hardhat/'

    response = requests.put(
        CHRONIX_URL + hardhat_path,
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

    requests.delete(CHRONIX_URL + hardhat_path, json={'port': port})


@pytest.fixture(scope="module")
def web3_with_dvt_module(web3_provider_integration):
    port = urlparse(web3_provider_integration.provider._hosts_uri[0]).port

    r = requests.post(CHRONIX_URL + 'v1/env/' + str(port) + '/simple-dvt/deploy/')

    assert r.status_code == 200

    r = requests.post(CHRONIX_URL + 'v1/env/' + str(port) + '/simple-dvt/add-node-operator/', json={
        'name': 'NOname',
        'norAddress': '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
        'rewardAddress': '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
    })

    assert r.status_code == 200

    r = requests.post(CHRONIX_URL + 'v1/env/' + str(port) + '/simple-dvt/add-node-operator-keys/')

    yield web3_provider_integration


@pytest.fixture(scope="module")
def web3_lido_integration(web3_provider_integration):
    web3_provider_integration.attach_modules({
        'lido': LidoContracts,
        'transaction': TransactionUtils,
    })
    yield web3_provider_integration
