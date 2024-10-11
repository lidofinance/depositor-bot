import pytest
import variables
from eth_account import Account
from eth_typing import BlockNumber
from fixtures import *  # noqa
from web3.types import BlockData, Wei

# https://etherscan.io/address/0xC77F8768774E1c9244BEed705C4354f2113CFc09#readContract#F12
DSM_OWNER = '0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c'
# https://goerli.etherscan.io/address/0xe57025E250275cA56f92d76660DEcfc490C7E79A#readContract#F12
# DSM_OWNER = '0xa5F1d7D49F581136Cf6e58B32cBE9a2039C48bA1'

COUNCIL_ADDRESS_1 = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8'
COUNCIL_PK_1 = '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d'

COUNCIL_ADDRESS_2 = '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC'
COUNCIL_PK_2 = '0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a'


@pytest.fixture
def block_data():
    yield BlockData(number=BlockNumber(10), baseFeePerGas=Wei(100))


@pytest.fixture
def set_account():
    variables.ACCOUNT = Account.from_key('0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80')
    yield variables.ACCOUNT
    variables.ACCOUNT = None


@pytest.fixture
def set_integration_account():
    # Basic Hardhat account
    # Address 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
    variables.ACCOUNT = Account.from_key('0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80')
    variables.CREATE_TRANSACTIONS = True
    yield
    variables.CREATE_TRANSACTIONS = False
    variables.ACCOUNT = None


@pytest.fixture
def ping_message():
    yield {
        'type': 'ping',
        'blockNumber': 13726495,
        'guardianIndex': 0,
        'guardianAddress': '0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A',
        'app': {'version': '1.1.1', 'name': 'lido-council-daemon'},
    }


@pytest.fixture
def add_accounts_to_guardian(web3_lido_integration, set_integration_account):
    web3_lido_integration.provider.make_request('anvil_impersonateAccount', [DSM_OWNER])
    web3_lido_integration.provider.make_request('anvil_setBalance', [DSM_OWNER, '0x500000000000000000000000'])

    web3_lido_integration.lido.deposit_security_module.functions.addGuardian(COUNCIL_ADDRESS_1, 2).transact({'from': DSM_OWNER})
    web3_lido_integration.lido.deposit_security_module.functions.addGuardian(COUNCIL_ADDRESS_2, 2).transact({'from': DSM_OWNER})

    yield web3_lido_integration
