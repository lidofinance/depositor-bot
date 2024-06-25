import logging

from eth_typing import Hash32
from web3.contract.contract import ContractFunction
from web3.types import Wei

from blockchain.contracts.base_interface import ContractInterface

logger = logging.getLogger(__name__)


class StakingModuleContract(ContractInterface):
    abi_path = './interfaces/StakingModule.json'

    def wseth(self) -> Wei:
        response = self.functions.wseth().call()
        logger.info({'msg': 'Call `wseth()`.', 'value': response})
        return response

    def get_staking_module_id(self) -> int:
        response = self.functions.stakingModuleId().call()
        logger.info({'msg': 'Call `stakingModuleId()`.', 'value': response})
        return response

    def convert_and_deposit(self,
                            block_number: int,
                            block_hash: Hash32,
                            deposit_root: Hash32,
                            nonce: int,
                            deposit_call_data: bytes,
                            guardian_signatures: tuple[tuple[str, str], ...]) -> ContractFunction:
        tx = self.functions.convertAndDeposit(
            None,
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
