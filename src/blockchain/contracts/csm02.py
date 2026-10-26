import logging

from web3.types import BlockIdentifier

from blockchain.contracts.base_interface import ContractInterface

logger = logging.getLogger(__name__)


class CSM02Contract(ContractInterface):
    abi_path = './interfaces/ICSM02.json'

    def get_keys_for_top_up(self, max_key_count: int, block_identifier: BlockIdentifier = 'latest') -> list[bytes]:
        """Fetch up to `max_key_count` validator pubkeys from the module's top-up queue, in queue order.

        Fewer than `max_key_count` are returned if the queue is shorter.
        """
        response = self.functions.getKeysForTopUp(max_key_count).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `getKeysForTopUp({max_key_count})`.',
                'keys_count': len(response),
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    def get_top_up_queue_capacity(self, block_identifier: BlockIdentifier = 'latest') -> int:
        """Free seats left in the top-up queue (limit - length). 0 means the queue is full, which
        caps the module's seed capacity to zero (getStakingModuleSummary)."""
        _enabled, limit, length, _head = self.functions.getTopUpQueue().call(block_identifier=block_identifier)
        capacity = limit - length
        logger.info(
            {
                'msg': 'Call `getTopUpQueue()`.',
                'limit': limit,
                'length': length,
                'capacity': capacity,
                'block_identifier': repr(block_identifier),
            }
        )
        return capacity
