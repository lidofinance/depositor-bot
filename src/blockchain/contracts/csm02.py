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
