import logging
from typing import cast

import variables
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_router import (
    StakingRouterContractV3,
    StakingRouterContractV4,
)
from blockchain.contracts.topup_gateway import TopUpGatewayContract
from web3 import Web3
from web3.contract.contract import Contract
from web3.module import Module

logger = logging.getLogger(__name__)


class LidoContracts(Module):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self.staking_router_version: int | None = None
        self.topup_gateway: TopUpGatewayContract | None = None
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
        if self.staking_router_version == 4:
            self._load_topup_gateway()

    def _load_staking_router(self):
        staking_router_address = self.lido_locator.staking_router()

        # Read version using V3 ABI (getContractVersion signature is the same across versions)
        sr = cast(
            StakingRouterContractV3,
            self.w3.eth.contract(
                address=staking_router_address,
                ContractFactoryClass=StakingRouterContractV3,
                decode_tuples=True,
            ),
        )
        self.staking_router_version = sr.get_contract_version()

        if self.staking_router_version == 4:
            logger.debug({'msg': 'Use staking router V4.'})
            self.staking_router = cast(
                StakingRouterContractV4,
                self.w3.eth.contract(
                    address=staking_router_address,
                    ContractFactoryClass=StakingRouterContractV4,
                    decode_tuples=True,
                ),
            )
        elif self.staking_router_version == 3:
            logger.debug({'msg': 'Use staking router V3.'})
            self.staking_router = sr
        else:
            raise ValueError(f'Unsupported StakingRouter version: {self.staking_router_version}')

    def _load_dsm(self):
        dsm_address = self.lido_locator.deposit_security_module()

        self.deposit_security_module = cast(
            DepositSecurityModuleContract,
            self.w3.eth.contract(
                address=dsm_address,
                ContractFactoryClass=DepositSecurityModuleContract,
            ),
        )

    def _load_topup_gateway(self):
        topup_gateway_address = self.lido_locator.top_up_gateway()
        self.topup_gateway: TopUpGatewayContract = cast(
            TopUpGatewayContract,
            self.w3.eth.contract(
                address=topup_gateway_address,
                ContractFactoryClass=TopUpGatewayContract,
            ),
        )
        logger.debug({'msg': 'Loaded TopUpGateway.', 'address': topup_gateway_address})
