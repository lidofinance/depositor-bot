import logging
from typing import cast

import variables
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContractV2
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_router import StakingRouterContract, StakingRouterContractV2
from web3 import Web3
from web3.contract.contract import Contract
from web3.module import Module

logger = logging.getLogger(__name__)


class LidoContracts(Module):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self._load_contracts()

    def has_contract_address_changed(self) -> bool:
        """If contracts changed all cache related to contracts should be cleared"""
        addresses = [contract.address for contract in self.__dict__.values() if isinstance(contract, Contract)]
        self._load_contracts()
        new_addresses = [contract.address for contract in self.__dict__.values() if isinstance(contract, Contract)]
        return addresses != new_addresses

    def _load_contracts(self):
        self.deposit_contract: DepositContract = cast(
            DepositContract,
            self.w3.eth.contract(
                address=variables.DEPOSIT_CONTRACT,
                ContractFactoryClass=DepositContract,
            ),
        )

        self.lido_locator: LidoLocatorContract = cast(
            LidoLocatorContract,
            self.w3.eth.contract(
                address=variables.LIDO_LOCATOR,
                ContractFactoryClass=LidoLocatorContract,
            ),
        )

        self.lido: LidoContract = cast(
            LidoContract,
            self.w3.eth.contract(
                address=self.lido_locator.lido(),
                ContractFactoryClass=LidoContract,
            ),
        )

        self.staking_router = cast(
            StakingRouterContract,
            self.w3.eth.contract(
                address=self.lido_locator.staking_router(),
                ContractFactoryClass=StakingRouterContractV2,
            ),
        )

        self.deposit_security_module = cast(
            DepositSecurityModuleContractV2,
            self.w3.eth.contract(
                address=self.lido_locator.deposit_security_module(),
                ContractFactoryClass=DepositSecurityModuleContractV2,
            ),
        )
