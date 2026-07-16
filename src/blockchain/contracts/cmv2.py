import logging

from blockchain.contracts.base_interface import ContractInterface
from web3.types import BlockIdentifier, Wei

logger = logging.getLogger(__name__)


class CMV2Contract(ContractInterface):
    abi_path = './interfaces/ICMV2.json'

    def get_deposits_allocation(
        self,
        deposit_amount: Wei,
        block_identifier: BlockIdentifier = 'latest',
    ) -> tuple:
        """Returns operator-level allocation for top-up.

        Returns:
            (allocated, operatorIds[], allocations[])
        """
        response = self.functions.getDepositsAllocation(
            deposit_amount,
        ).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `getDepositsAllocation({deposit_amount})`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response
