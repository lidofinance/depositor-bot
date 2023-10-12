from typing import cast

from web3 import Web3
from web3.module import Module

import variables
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_router import StakingRouterContract


class LidoContracts(Module):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self._load_contracts()

    def _load_contracts(self):
        self.deposit_contract: DepositContract = cast(DepositContract, self.w3.eth.contract(
            address=variables.DEPOSIT_CONTRACT,
            ContractFactoryClass=DepositContract,
        ))

        self.lido_locator: LidoLocatorContract = cast(LidoLocatorContract, self.w3.eth.contract(
            address=variables.LIDO_LOCATOR,
            ContractFactoryClass=LidoLocatorContract,
        ))

        self.lido: LidoContract = cast(LidoContract, self.w3.eth.contract(
            address=self.lido_locator.lido(),
            ContractFactoryClass=LidoContract,
        ))

        self.deposit_security_module = cast(DepositSecurityModuleContract, self.w3.eth.contract(
            address=self.lido_locator.deposit_security_module(),
            ContractFactoryClass=DepositSecurityModuleContract,
        ))

        self.staking_router = cast(StakingRouterContract, self.w3.eth.contract(
            address=self.lido_locator.staking_router(),
            ContractFactoryClass=StakingRouterContract,
        ))
