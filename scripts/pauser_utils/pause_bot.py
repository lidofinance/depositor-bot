import logging
import time
from typing import List

from brownie import chain, web3
from web3.exceptions import BlockNotFound

from scripts.pauser_utils.kafka import PauseBotMsgRecipient
from scripts.utils.interfaces import DepositSecurityModuleInterface
from scripts.utils.metrics import CREATING_TRANSACTIONS, BUILD_INFO
from scripts.utils import variables


logger = logging.getLogger(__name__)


class DepositPauseBot:
    def __init__(self):
        logger.info({'msg': 'Initialize DepositPauseBot.'})

        self.kafka = PauseBotMsgRecipient(client=f'{variables.KAFKA_GROUP_PREFIX}pause')

        # Some rarely change things
        self._load_constants()
        logger.info({'msg': 'DepositPauseBot bot initialize done.'})

        BUILD_INFO.labels(
            'Pauser bot',
            variables.NETWORK,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            variables.KAFKA_TOPIC,
            variables.ACCOUNT.address if variables.ACCOUNT else '0x0',
            variables.CREATE_TRANSACTIONS,
        )

    def __del__(self):
        del self.kafka

    def _load_constants(self):
        self.blocks_till_pause_is_valid = DepositSecurityModuleInterface.getPauseIntentValidityPeriodBlocks()
        logger.info({
            'msg': f'Call `getPauseIntentValidityPeriodBlocks()`.',
            'value': self.blocks_till_pause_is_valid
        })

        if variables.CREATE_TRANSACTIONS:
            CREATING_TRANSACTIONS.labels('pause').set(1)
        else:
            CREATING_TRANSACTIONS.labels('pause').set(0)

    # ------------ CYCLE STAFF -------------------
    def run_as_daemon(self):
        """Super-Mega infinity cycle!"""
        while True:
            try:
                for _ in chain.new_blocks():
                    self.run_cycle()
            except BlockNotFound as error:
                logger.warning({'msg': 'Fetch block exception (BlockNotFound)', 'error': str(error)})
                time.sleep(10)

    def run_cycle(self):
        """
        Fetch latest signs from
        """
        self._update_current_block()

        # Pause message instantly if we receive pause message
        pause_messages = self.kafka.get_pause_messages(self._current_block.number, self.blocks_till_pause_is_valid)

        if pause_messages and not self.protocol_is_paused:
            self.pause_deposits_with_messages(pause_messages)

    def _update_current_block(self):
        self._current_block = web3.eth.get_block('latest')
        logger.info({'msg': f'Fetch `latest` block.', 'value': self._current_block.number})

        self.protocol_is_paused = DepositSecurityModuleInterface.isPaused(
            block_identifier=self._current_block.hash.hex(),
        )
        logger.info({'msg': f'Call `isPaused()`.', 'value': self.protocol_is_paused})

        self.kafka.update_messages()

    # ----------- DO PAUSE ----------------
    def pause_deposits_with_messages(self, messages: List[dict]):
        logger.warning({'msg': 'Message pause protocol initiate.', 'value': messages})
        for message in messages:
            priority_fee = web3.eth.max_priority_fee * 2

            logger.info({
                'msg': 'Send pause transaction.',
                'values': {
                    'block_number': message['blockNumber'],
                    'signature': (message['signature']['r'], message['signature']['_vs']),
                    'priority_fee': priority_fee,
                },
            })

            if not variables.ACCOUNT:
                logger.warning({'msg': 'No account provided. Skip creating tx.'})
                return

            if not variables.CREATE_TRANSACTIONS:
                logger.warning({'msg': 'Running in DRY mode.'})
                return

            logger.info({'msg': 'Creating tx in blockchain.'})
            try:
                result = DepositSecurityModuleInterface.pauseDeposits(
                    message['blockNumber'],
                    (message['signature']['r'], message['signature']['_vs']),
                    {
                        'priority_fee': priority_fee,
                    },
                )
            except BaseException as error:
                logger.error({'msg': f'Pause error.', 'error': str(error), 'value': message})
            else:
                logger.warning({'msg': 'Protocol was paused', 'value': str(result.logs)})
                break

        # Cleanup kafka, no need to deposit for now
        self.kafka.clear_pause_messages()
