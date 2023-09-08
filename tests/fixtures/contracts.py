from typing import cast

import pytest

import variables
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.staking_router import StakingRouterContract


@pytest.fixture
def lido_locator(web3_provider_integration):
    yield cast(LidoLocatorContract, web3_provider_integration.eth.contract(
        # ToDo provide lido locator address via env variable
        address=variables.LIDO_LOCATOR,
        ContractFactoryClass=LidoLocatorContract,
    ))


@pytest.fixture
def deposit_contract(web3_provider_integration):
    yield cast(DepositContract, web3_provider_integration.eth.contract(
        address=variables.DEPOSIT_CONTRACT,
        ContractFactoryClass=DepositContract,
    ))


@pytest.fixture
def lido_contract(web3_provider_integration, lido_locator):
    yield cast(LidoContract, web3_provider_integration.eth.contract(
        address=lido_locator.lido(),
        ContractFactoryClass=LidoContract,
    ))


@pytest.fixture
def deposit_security_module(web3_provider_integration, lido_locator):
    yield cast(DepositSecurityModuleContract, web3_provider_integration.eth.contract(
        address=lido_locator.deposit_security_module(),
        ContractFactoryClass=DepositSecurityModuleContract,
    ))


@pytest.fixture
def staking_router(web3_provider_integration, lido_locator):
    yield cast(StakingRouterContract, web3_provider_integration.eth.contract(
        address=lido_locator.staking_router(),
        ContractFactoryClass=StakingRouterContract,
    ))
