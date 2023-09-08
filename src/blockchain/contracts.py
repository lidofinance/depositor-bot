import json

from web3 import Web3

from blockchain.constants import LIDO_LOCATOR, NODE_OPS_ADDRESSES, DEPOSIT_CONTRACT
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

        self.lido_locator = w3.eth.contract(
            address=LIDO_LOCATOR[WEB3_CHAIN_ID],
            abi=load_abi(abi_path, 'LidoLocator'),
        )

        self.lido = w3.eth.contract(
            address=self.lido_locator.functions.lido().call(),
            abi=load_abi(abi_path, 'Lido'),
        )

        self.deposit_security_module = w3.eth.contract(
            address=self.lido_locator.functions.depositSecurityModule().call(),
            abi=load_abi(abi_path, 'DepositSecurityModule'),
        )

        self.staking_router = w3.eth.contract(
            address=self.lido_locator.functions.stakingRouter().call(),
            abi=load_abi(abi_path, 'StakingRouter'),
        )

        self.deposit_contract = w3.eth.contract(
            address=DEPOSIT_CONTRACT[WEB3_CHAIN_ID],
            abi=load_abi(abi_path, 'DepositContract'),
        )

        # TODO remove after get_nonce will be replaced with staking call
        self.node_operator_registry = w3.eth.contract(
            address=NODE_OPS_ADDRESSES[WEB3_CHAIN_ID],
            abi=load_abi(abi_path, 'NodeOperatorRegistry'),
        )

    @staticmethod
    def load_abi(abi_name):
        f = open(f'../../interfaces/{abi_name}.json')
        return json.load(f)


contracts = Contracts()
