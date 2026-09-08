import logging

from web3.types import BlockIdentifier, Wei

from blockchain.contracts.base_interface import ContractInterface

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

    def get_key_allocated_balances(
        self,
        node_operator_id: int,
        start_index: int,
        keys_count: int,
        block_identifier: BlockIdentifier = 'latest',
    ) -> list[int]:
        """Module-tracked top-up balance (wei, above the 32 ETH activation) for keys
        [start_index, start_index + keys_count) of an operator.
        """
        response = self.functions.getKeyAllocatedBalances(node_operator_id, start_index, keys_count).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `getKeyAllocatedBalances({node_operator_id}, {start_index}, {keys_count})`.',
                'balances_count': len(response),
                'block_identifier': repr(block_identifier),
            }
        )
        return response
