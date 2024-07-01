import logging

from blockchain.contracts.base_interface import ContractInterface
from eth_typing import BlockIdentifier, ChecksumAddress
from web3.types import Wei

logger = logging.getLogger(__name__)


class ERC20Contract(ContractInterface):
    abi_path = './interfaces/ERC20.json'

    def balance_of(self, address: ChecksumAddress, block_identifier: BlockIdentifier = 'latest') -> Wei:
        response = self.functions.balanceOf(address).call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `balanceOf()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response
