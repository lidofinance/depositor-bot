import pytest
from eth_account import Account
from eth_typing import BlockNumber
from web3.types import BlockData, Wei

from tests.fixtures.provider import *
from tests.fixtures.contracts import *


@pytest.fixture
def block_data():
    yield BlockData(number=BlockNumber(10), baseFeePerGas=Wei(100))


@pytest.fixture
def set_account():
    variables.ACCOUNT = Account.from_key('0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80')
    yield variables.ACCOUNT
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
