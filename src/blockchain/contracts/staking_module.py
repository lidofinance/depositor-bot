import logging
from typing import cast

from blockchain.contracts.base_interface import ContractInterface
from blockchain.contracts.erc20 import ERC20Contract
from eth_typing import BlockIdentifier, ChecksumAddress

logger = logging.getLogger(__name__)


class StakingModuleContract(ContractInterface):
    abi_path = './interfaces/StakingModule.json'

    def weth(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.weth().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `weth()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def get_staking_module_id(self, block_identifier: BlockIdentifier = 'latest') -> int:
        response = self.functions.stakingModuleId().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `stakingModuleId()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    @property
    def weth_contract(self) -> ERC20Contract:
        return cast(
            ERC20Contract,
            self.w3.eth.contract(
                address=self.weth(),
                ContractFactoryClass=ERC20Contract,
            ),
        )
