import logging
from typing import cast

from blockchain.contracts.base_interface import ContractInterface
from eth_typing import ChecksumAddress
from web3.types import BlockIdentifier

from blockchain.contracts.withdrawal_queue import WithdrawalQueueContract

logger = logging.getLogger(__name__)


class LidoLocatorContract(ContractInterface):
    abi_path = './interfaces/LidoLocator.json'

    def lido(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.lido().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `lido()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def deposit_security_module(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.depositSecurityModule().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `depositSecurityModule()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def staking_router(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.stakingRouter().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `stakingRouter()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def withdrawal_queue(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        response = self.functions.withdrawalQueue().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `withdrawalQueue()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    @property
    def withdrawal_queue_contract(self) -> WithdrawalQueueContract:
        return cast(
            WithdrawalQueueContract,
            self.w3.eth.contract(
                address=self.withdrawal_queue(),
                ContractFactoryClass=WithdrawalQueueContract,
            ),
        )
