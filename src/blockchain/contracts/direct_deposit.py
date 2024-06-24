import logging

from blockchain.contracts.base_interface import ContractInterface
from eth_typing import Hash32
from web3.contract.contract import ContractFunction
from web3.types import BlockIdentifier

logger = logging.getLogger(__name__)


class DirectDepositContract(ContractInterface):
    abi_path = './interfaces/DirectDepositContract.json'

    def get_staking_module_id(self, block_identifier: BlockIdentifier = 'latest') -> int:
        pass

    def convert_and_deposit(self, block_number: int,
                            block_hash: Hash32,
                            deposit_root: Hash32,
                            nonce: int,
                            deposit_call_data: bytes,
                            guardian_signatures: tuple[tuple[str, str], ...]) -> ContractFunction:
        pass
