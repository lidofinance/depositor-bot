from eth_account import Account
from eth_typing import BlockNumber
from web3.types import BlockData, Wei

from fixtures import *

# https://etherscan.io/address/0xC77F8768774E1c9244BEed705C4354f2113CFc09#readContract#F12
DSM_OWNER = '0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c'
# https://goerli.etherscan.io/address/0xe57025E250275cA56f92d76660DEcfc490C7E79A#readContract#F12
# DSM_OWNER = '0xa5F1d7D49F581136Cf6e58B32cBE9a2039C48bA1'


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


@pytest.fixture()
def ping_message(monkeypatch):
    yield {
        "type": "ping",
        "blockNumber": 13726495,
        "guardianIndex": 0,
        "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
        "app": {
            "version": "1.1.1",
            "name": "lido-council-daemon"
        }
    }
