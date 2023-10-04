import json
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

    response = requests.post(
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

    yield Web3(FallbackProvider([f'http://0.0.0.0:{port}/'], request_kwargs={'timeout': 3600}))

    r = requests.delete(CHRONIX_URL + hardhat_path + f'{port}/')

    assert r.status_code == 200


@pytest.fixture(scope="module")
def web3_lido_integration(web3_provider_integration):
    web3_provider_integration.attach_modules({
        'lido': LidoContracts,
        'transaction': TransactionUtils,
    })
    yield web3_provider_integration


@pytest.fixture(scope="module")
def web3_with_dvt_module(web3_lido_integration):
    port = urlparse(web3_lido_integration.provider._hosts_uri[0]).port

    r1 = requests.post(CHRONIX_URL + 'v1/env/' + str(port) + '/simple-dvt/deploy/')

    print(r1.text)
    assert r1.status_code == 200

    r2 = requests.post(CHRONIX_URL + 'v1/env/' + str(port) + '/simple-dvt/add-node-operator/', json={
        'name': 'NOname',
        'norAddress': r1.json()['data']['stakingRouterData']['stakingModules'][1]['stakingModuleAddress'],
        'rewardAddress': '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
    })

    print(r2.text)
    assert r2.status_code == 200

    r3 = requests.post(CHRONIX_URL + 'v1/env/' + str(port) + '/simple-dvt/add-node-operator-keys/', json={
        'noId': r2.json()['data']['nodeOperatorId'],
        'norAddress': r1.json()['data']['stakingRouterData']['stakingModules'][1]['stakingModuleAddress'],
        'keysCount': 100,
        'keys': '0x' + 'a04f11ab318a981d4b629ac91662b865b89d6cb2ae4661daeec5fb92b2d332028732f461eb685f522ace9953d48f72fe' * 100,
        'signatures': '0x' + 'b5cc6f8d28eed18bef327781a804b4137cabdf289c9d65101439ba5c937b6d313125053faa896be9f3730add8d107ed5055ed9e16993b190d21f51ce36d71921985f7831239e07760f00dd298b3b4e7f5b13131649fe0c33b0388cd2c7719b56' * 100,
    })
    assert r3.status_code == 200

    with open('interfaces/NodeOperatorRegistry.json', 'r') as f:
        staking_module = web3_lido_integration.eth.contract(
            r1.json()['data']['stakingRouterData']['stakingModules'][1]['stakingModuleAddress'],
            abi=json.loads(f.read())
        )

    staking_module.functions.setNodeOperatorStakingLimit(r2.json()['data']['nodeOperatorId'], 100).transact({
        'from': '0x2e59A20f205bB85a89C53f1936454680651E618e'
    })

    for _ in range(web3_lido_integration.lido.deposit_security_module.functions.getMinDepositBlockDistance().call()):
        web3_lido_integration.provider.make_request('hardhat_mine', [])

    yield web3_lido_integration
