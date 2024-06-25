import logging

from eth_typing import ChecksumAddress

from blockchain.contracts.base_interface import ContractInterface

logger = logging.getLogger(__name__)


class ERC20Contract(ContractInterface):
    abi_path = './interfaces/ERC20.json'

    def balance_of(self, address: ChecksumAddress) -> int:
        response = self.functions.balanceOf(address).call()
        logger.info({'msg': 'Call `balanceOf()`.', 'value': response})
        return response
