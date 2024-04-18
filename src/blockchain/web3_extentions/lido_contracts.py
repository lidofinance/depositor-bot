import logging
from typing import cast

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.module import Module

import variables
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract, DepositSecurityModuleContractV2
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_router import StakingRouterContract


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

        dsm_address = self.lido_locator.deposit_security_module()

        self.deposit_security_module = cast(DepositSecurityModuleContractV2, self.w3.eth.contract(
            address=dsm_address,
            ContractFactoryClass=DepositSecurityModuleContractV2,
        ))

        try:
            self.deposit_security_module.functions.VERSION().call()
        except ContractLogicError:
            logger.info({'msg': 'Use deposit security module V1.'})
            self.deposit_security_module = cast(DepositSecurityModuleContract, self.w3.eth.contract(
                address=dsm_address,
                ContractFactoryClass=DepositSecurityModuleContract,
            ))
        else:
            logger.info({'msg': 'Use deposit security module V2.'})
