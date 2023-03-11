import json

from web3 import Web3

from blockchain.constants import (
    LIDO_CONTRACT_ADDRESSES,
    NODE_OPS_ADDRESSES,
    DEPOSIT_SECURITY_MODULE,
    DEPOSIT_CONTRACT,
    STAKING_ROUTER,
)
from variables import WEB3_CHAIN_ID


def load_abi(abi_path, abi_name):
    f = open(f'{abi_path}{abi_name}.json')
    return json.load(f)


class Contracts:
    __initialized = False

    lido = None
    node_operator_registry = None
    deposit_security_module = None
    deposit_contract = None
    staking_router = None

    def initialize(self, w3: Web3, abi_path='./interfaces/'):
        __initialized = True

        self.lido = w3.eth.contract(
            address=LIDO_CONTRACT_ADDRESSES[WEB3_CHAIN_ID],
            abi=load_abi(abi_path, 'Lido'),
        )
        self.node_operator_registry = w3.eth.contract(
            address=NODE_OPS_ADDRESSES[WEB3_CHAIN_ID],
            abi=load_abi(abi_path, 'NodeOperatorRegistry'),
        )

        self.deposit_security_module = w3.eth.contract(
            address=DEPOSIT_SECURITY_MODULE[WEB3_CHAIN_ID],
            abi=load_abi(abi_path, 'DepositSecurityModule'),
        )

        self.deposit_contract = w3.eth.contract(
            address=DEPOSIT_CONTRACT[WEB3_CHAIN_ID],
            abi=load_abi(abi_path, 'DepositContract'),
        )

        self.staking_router = w3.eth.contract(
            address=STAKING_ROUTER[WEB3_CHAIN_ID],
            abi=load_abi(abi_path, 'StakingRouter'),
        )

    @staticmethod
    def load_abi(abi_name):
        f = open(f'../../interfaces/{abi_name}.json')
        return json.load(f)


contracts = Contracts()
