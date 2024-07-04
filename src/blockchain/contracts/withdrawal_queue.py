import logging

from blockchain.contracts.base_interface import ContractInterface
from web3.types import BlockIdentifier, Wei

logger = logging.getLogger(__name__)


class WithdrawalQueueContract(ContractInterface):
    abi_path = './interfaces/WithdrawalQueue.json'

    def unfinalized_st_eth(self, block_identifier: BlockIdentifier = 'latest') -> Wei:
        """
        Returns unfinalizedStETH ether amount.
        """
        response = self.functions.unfinalizedStETH().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `unfinalizedStETH()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response
