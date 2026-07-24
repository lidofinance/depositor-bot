from typing import cast

import pytest
import variables
from blockchain.contracts.cmv2 import CMV2Contract
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract
from blockchain.contracts.erc20 import ERC20Contract
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_router import StakingRouterContractV4
from blockchain.contracts.topup_gateway import TopUpGatewayContract


@pytest.fixture
def lido_locator(web3_provider_integration):
    yield cast(
        LidoLocatorContract,
        web3_provider_integration.eth.contract(
            address=variables.LIDO_LOCATOR,
            ContractFactoryClass=LidoLocatorContract,
        ),
    )


@pytest.fixture
def deposit_contract(web3_provider_integration):
    yield cast(
        DepositContract,
        web3_provider_integration.eth.contract(
            address=variables.DEPOSIT_CONTRACT,
            ContractFactoryClass=DepositContract,
        ),
    )


@pytest.fixture
def lido_contract(web3_provider_integration, lido_locator):
    yield cast(
        LidoContract,
        web3_provider_integration.eth.contract(
            address=lido_locator.lido(),
            ContractFactoryClass=LidoContract,
        ),
    )


@pytest.fixture
def deposit_security_module(web3_provider_integration, lido_locator):
    yield cast(
        DepositSecurityModuleContract,
        web3_provider_integration.eth.contract(
            address=lido_locator.deposit_security_module(),
            ContractFactoryClass=DepositSecurityModuleContract,
        ),
    )


@pytest.fixture
def staking_router(web3_provider_integration, lido_locator):
    yield cast(
        StakingRouterContractV4,
        web3_provider_integration.eth.contract(
            address=lido_locator.staking_router(),
            ContractFactoryClass=StakingRouterContractV4,
        ),
    )


@pytest.fixture
def topup_gateway(web3_provider_integration, lido_locator):
    yield cast(
        TopUpGatewayContract,
        web3_provider_integration.eth.contract(
            address=lido_locator.top_up_gateway(),
            ContractFactoryClass=TopUpGatewayContract,
        ),
    )


@pytest.fixture
def cmv2_contract(web3_lido_integration):
    module_digests = web3_lido_integration.lido.staking_router.get_all_staking_module_digests()
    cmv2_type = b'curated-onchain-v2'.ljust(32, b'\x00')

    for digest in module_digests:
        module_address = digest['address']
        if web3_lido_integration.lido.staking_module(digest['module_id']).get_type() == cmv2_type:
            yield cast(
                CMV2Contract,
                web3_lido_integration.eth.contract(
                    address=module_address,
                    ContractFactoryClass=CMV2Contract,
                ),
            )
            return

    pytest.fail('No CMV2 module found on the current RPC target.')


@pytest.fixture
def weth(web3_provider_integration, staking_module):
    yield cast(
        ERC20Contract,
        web3_provider_integration.eth.contract(
            address=staking_module.weth(),
            ContractFactoryClass=ERC20Contract,
        ),
    )
