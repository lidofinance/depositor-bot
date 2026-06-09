import logging

from blockchain.contracts.base_interface import ContractInterface
from web3.types import BlockIdentifier, Wei

logger = logging.getLogger(__name__)


class LidoContract(ContractInterface):
    abi_path = './interfaces/Lido.json'

    def get_depositable_ether(self, block_identifier: BlockIdentifier = 'latest') -> Wei:
        """
        Returns depositable ether amount.
        Unfinalized stETH required by WithdrawalQueue are excluded from buffered ether.
        """
        response = self.functions.getDepositableEther().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getDepositableEther()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def get_buffered_ether(self, block_identifier: BlockIdentifier = 'latest') -> Wei:
        """
        Get the amount of Ether temporary buffered on this contract balance.
        """
        response = self.functions.getBufferedEther().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getBufferedEther()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def can_deposit(self, block_identifier: BlockIdentifier = 'latest') -> bool:
        """Whether Lido currently allows deposits (not stopped / not bunker, etc.)."""
        response = self.functions.canDeposit().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `canDeposit()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response
