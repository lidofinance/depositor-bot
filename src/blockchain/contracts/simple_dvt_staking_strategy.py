import logging
from typing import cast

from blockchain.contracts.base_interface import ContractInterface
from blockchain.contracts.staking_module import StakingModuleContract
from eth_typing import BlockIdentifier, ChecksumAddress, Hash32
from web3.contract.contract import ContractFunction

logger = logging.getLogger(__name__)


class SimpleDVTStakingStrategyContract(ContractInterface):
    abi_path = './interfaces/SimpleDVTStakingStrategy.json'

    def vault(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.vault().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `vault()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def get_staking_module(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.stakingModule().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `stakingModule()`.', 'value': response, 'block_identifier': repr(block_identifier)})
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
    def staking_module_contract(self) -> StakingModuleContract:
        return cast(
            StakingModuleContract,
            self.w3.eth.contract(
                address=self.get_staking_module(),
                ContractFactoryClass=StakingModuleContract,
            )
        )
