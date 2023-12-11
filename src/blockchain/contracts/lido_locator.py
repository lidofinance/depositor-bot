import logging

from eth_typing import ChecksumAddress
from web3.types import BlockIdentifier

from blockchain.contracts.base_interface import ContractInterface


logger = logging.getLogger(__name__)


class LidoLocatorContract(ContractInterface):
    abi_path = './interfaces/LidoLocator.json'

    def lido(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.lido().call(block_identifier=block_identifier)
        logger.info({'msg': f'Call `lido()`.', 'value': response, 'block_identifier': block_identifier.__repr__()})
        return response

    def deposit_security_module(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.depositSecurityModule().call(block_identifier=block_identifier)
        logger.info({'msg': f'Call `depositSecurityModule()`.', 'value': response, 'block_identifier': block_identifier.__repr__()})
        return response

    def staking_router(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.stakingRouter().call(block_identifier=block_identifier)
        logger.info({'msg': f'Call `stakingRouter()`.', 'value': response, 'block_identifier': block_identifier.__repr__()})
        return response
