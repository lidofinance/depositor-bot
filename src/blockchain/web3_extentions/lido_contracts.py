from typing import cast

from web3 import Web3
from web3.module import Module

from blockchain.constants import LIDO_LOCATOR, DEPOSIT_CONTRACT
from blockchain.contracts.deposit import DepositContract

from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_router import StakingRouterContract
from variables import WEB3_CHAIN_ID


class LidoContracts(Module):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self._load_contracts()

    def _load_contracts(self):
        self.deposit_contract: DepositContract = cast(DepositContract, self.web3.eth.contract(
            address=DEPOSIT_CONTRACT[self.web3.eth.chain_id],
            ContractFactoryClass=DepositContract,
        ))

        self.lido_locator: LidoLocatorContract = cast(LidoLocatorContract, self.web3.eth.contract(
            # ToDo provide lido locator address via env variable
            address=LIDO_LOCATOR[self.web3.eth.chain_id],
            ContractFactoryClass=LidoLocatorContract,
        ))

        self.lido: LidoContract = cast(LidoContract, self.web3.eth.contract(
            address=self.lido_locator.lido(),
            ContractFactoryClass=LidoContract,
        ))

        self.deposit_security_module = cast(DepositSecurityModuleContract, self.web3.eth.contract(
            address=self.lido_locator.deposit_security_module(),
            ContractFactoryClass=DepositSecurityModuleContract,
        ))

        self.staking_router = cast(StakingRouterContract, self.web3.eth.contract(
            address=self.lido_locator.staking_router(),
            ContractFactoryClass=StakingRouterContract,
        ))
