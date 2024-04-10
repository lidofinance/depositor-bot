import os
from typing import cast

from web3 import Web3
from web3.contract import Contract
from web3.module import Module

import variables
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract, DepositSecurityModuleContractV2
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_router import StakingRouterContract


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

        self.staking_router = cast(StakingRouterContract, self.w3.eth.contract(
            address=self.lido_locator.staking_router(),
            ContractFactoryClass=StakingRouterContract,
        ))

        # Since we don't have any version in contracts, addresses is the only chance to correctly handle upgrade
        dsm_v = os.getenv('DEPOSIT_SECURITY_MODULE_VERSION', None)
        dsm_address = self.lido_locator.deposit_security_module()
        if dsm_v == '1':
            self.deposit_security_module = cast(DepositSecurityModuleContract, self.w3.eth.contract(
                address=dsm_address,
                ContractFactoryClass=DepositSecurityModuleContract,
            ))
        elif dsm_v == '2':
            self.deposit_security_module = cast(DepositSecurityModuleContractV2, self.w3.eth.contract(
                address=dsm_address,
                ContractFactoryClass=DepositSecurityModuleContractV2,
            ))
        elif dsm_address in [
            '0xC77F8768774E1c9244BEed705C4354f2113CFc09',  # mainnet
            '0xe57025E250275cA56f92d76660DEcfc490C7E79A',  # goerli
            '0x045dd46212A178428c088573A7d102B9d89a022A',  # holesky
            '0x6885E36BFcb68CB383DfE90023a462C03BCB2AE5',  # sepolia
        ]:
            self.deposit_security_module = cast(DepositSecurityModuleContract, self.w3.eth.contract(
                address=dsm_address,
                ContractFactoryClass=DepositSecurityModuleContract,
            ))
        else:
            self.deposit_security_module = cast(DepositSecurityModuleContractV2, self.w3.eth.contract(
                address=dsm_address,
                ContractFactoryClass=DepositSecurityModuleContractV2,
            ))
