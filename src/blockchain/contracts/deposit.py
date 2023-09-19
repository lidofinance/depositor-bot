import logging

from eth_typing import BlockIdentifier, Hash32

from blockchain.contracts.base_interface import ContractInterface

logger = logging.getLogger(__name__)


class DepositContract(ContractInterface):
    abi_path = './interfaces/DepositContract.json'

    def get_deposit_root(self, block_identifier: BlockIdentifier = 'latest') -> Hash32:
        """
        Query the current deposit root hash.
        """
        response = self.functions.get_deposit_root().call(block_identifier=block_identifier)
        logger.info({
            'msg': f'Call `get_deposit_root()`.',
            'value': response.hex(),
            'block_identifier': repr(block_identifier),
        })
        return response
