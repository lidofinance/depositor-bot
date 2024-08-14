import logging
from typing import cast

from web3.contract.contract import ContractFunction

from blockchain.contracts.base_interface import ContractInterface
from blockchain.contracts.erc20 import ERC20Contract
from eth_typing import BlockIdentifier, ChecksumAddress, Hash32

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

    def convert_and_deposit(
        self,
        block_number: int,
        block_hash: Hash32,
        deposit_root: Hash32,
        nonce: int,
        deposit_call_data: bytes,
        guardian_signatures: tuple[tuple[str, str], ...]
    ) -> ContractFunction:
        tx = self.functions.convertAndDeposit(
            block_number,
            block_hash,
            deposit_root,
            nonce,
            deposit_call_data,
            guardian_signatures,
        )
        logger.info(
            {
                'msg': f'Build `convertAndDeposit({block_number}, {block_hash}, {deposit_root}, '
                       f'{nonce}, {deposit_call_data}, {guardian_signatures})` tx.'  # noqa
            }
        )
        return tx

    @property
    def weth_contract(self) -> ERC20Contract:
        return cast(
            ERC20Contract,
            self.w3.eth.contract(
                address=self.weth(),
                ContractFactoryClass=ERC20Contract,
            ),
        )
