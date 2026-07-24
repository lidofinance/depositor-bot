import logging
from typing import cast

import variables
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_module import StakingModuleContract
from blockchain.contracts.staking_router import StakingRouterContractV4
from blockchain.contracts.topup_gateway import TopUpGatewayContract
from web3 import Web3
from web3.contract.contract import Contract
from web3.module import Module

logger = logging.getLogger(__name__)

SUPPORTED_DSM_VERSION = 4


class LidoContracts(Module):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self._staking_module_cache: dict[int, StakingModuleContract] = {}
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
        self._load_staking_router()
        self._load_dsm()
        self._load_topup_gateway()
        self._load_staking_modules()

    def _load_staking_router(self):
        self.staking_router = cast(
            StakingRouterContractV4,
            self.w3.eth.contract(
                address=self.lido_locator.staking_router(),
                ContractFactoryClass=StakingRouterContractV4,
                decode_tuples=True,
            ),
        )

    def _load_dsm(self):
        dsm_address = self.lido_locator.deposit_security_module()

        self.deposit_security_module = cast(
            DepositSecurityModuleContract,
            self.w3.eth.contract(
                address=dsm_address,
                ContractFactoryClass=DepositSecurityModuleContract,
            ),
        )

        self.dsm_version = self.deposit_security_module.version()
        if self.dsm_version != SUPPORTED_DSM_VERSION:
            raise ValueError(f'Unsupported DSM version: {self.dsm_version} (expected {SUPPORTED_DSM_VERSION})')

    def _load_staking_modules(self):
        """Pre-load StakingModuleContract instances for all whitelisted modules."""
        self._staking_module_cache.clear()
        digests = self.staking_router.get_all_staking_module_digests()
        for digest in digests:
            module_id = digest['module_id']
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            checksum = self.w3.to_checksum_address(digest['address'])
            self._staking_module_cache[module_id] = cast(
                StakingModuleContract,
                self.w3.eth.contract(address=checksum, ContractFactoryClass=StakingModuleContract),
            )
        logger.debug({'msg': 'Loaded staking modules for whitelist.', 'ids': list(self._staking_module_cache.keys())})

    def staking_module(self, module_id: int) -> StakingModuleContract:
        """Returns the cached StakingModuleContract for the given module id."""
        return self._staking_module_cache[module_id]

    def _load_topup_gateway(self):
        topup_gateway_address = self.lido_locator.top_up_gateway()
        self.topup_gateway = cast(
            TopUpGatewayContract,
            self.w3.eth.contract(
                address=topup_gateway_address,
                ContractFactoryClass=TopUpGatewayContract,
            ),
        )
        logger.debug({'msg': 'Loaded TopUpGateway.', 'address': topup_gateway_address})
