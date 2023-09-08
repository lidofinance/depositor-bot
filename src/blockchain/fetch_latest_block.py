import logging
import time

from web3 import Web3
from web3.types import BlockData


logger = logging.getLogger(__name__)


def fetch_latest_block(w3: Web3, _prev_block_number: int) -> BlockData:
    from_provider_index = w3.provider._current_provider_index

    while True:
        current_block = w3.eth.get_block('latest')
        logger.info({'msg': f'Fetch `latest` block.', 'value': current_block.number})

        if _prev_block_number != current_block.number:
            return current_block

        w3.provider._current_provider_index = (w3.provider._current_provider_index + 1) % len(w3.provider._hosts_uri)

        if from_provider_index == w3.provider._current_provider_index:
            logger.info({'msg': f'All providers returns same block. Sleep for 5 seconds and try again.'})
            time.sleep(5)
