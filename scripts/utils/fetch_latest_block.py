import logging

from brownie import web3
from web3_multi_provider import MultiHTTPProvider

from scripts.utils.exceptions import StuckException

logger = logging.getLogger(__name__)


def fetch_latest_block(_prev_block_number):
    _current_block = web3.eth.get_block('latest')
    logger.info({'msg': f'Fetch `latest` block.', 'value': _current_block.number})

    if _prev_block_number != _current_block.number:
        # All ok
        return _current_block

    if not isinstance(web3.provider, MultiHTTPProvider):
        # If default provider is active (infura)
        raise StuckException('Default provider returns same block number.')

    # if MultiHTTPProvider - try to iterate and find one that retuns another block
    begin_provider_index = web3.provider._current_provider_index

    while True:
        web3.provider._current_provider_index = (web3.provider._current_provider_index + 1) % len(web3.provider._hosts_uri)

        _current_block = web3.eth.get_block('latest')
        logger.info({'msg': f'Fetch `latest` block.', 'value': _current_block.number})
        if _prev_block_number != _current_block.number:
            return _current_block
        elif begin_provider_index == web3.provider._current_provider_index:
            raise StuckException('All providers returns same block.')
