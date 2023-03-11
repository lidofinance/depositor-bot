import logging
import time
from typing import List

import timeout_decorator
from schema import Schema, Or
from web3 import Web3
from web3.exceptions import BlockNotFound, ContractLogicError
from web3_multi_provider import NoActiveProviderError

import variables
from blockchain.contracts import contracts
from blockchain.fetch_latest_block import fetch_latest_block
from cryptography.verify_signature import compute_vs
from metrics import healthcheck_pulse
from metrics.metrics import BUILD_INFO
from metrics.transport_message_metrics import message_metrics
from transport.msg_providers.kafka import KafkaMessageProvider
from transport.msg_providers.rabbit import RabbitProvider, MessageType
from transport.msg_schemas import PauseMessageSchema, get_pause_messages_sign_filter, PauseMessage, PingMessageSchema
from transport.msg_storage import MessageStorage
from variables_types import TransportType

logger = logging.getLogger(__name__)


class PauserBot:
    current_block = None

    def __init__(self, w3: Web3):
        logger.info({'msg': 'Initialize PauserBot.'})
        self.w3 = w3

        self.blocks_till_pause_is_valid = contracts.deposit_security_module.functions.getPauseIntentValidityPeriodBlocks().call()
        logger.info({
            'msg': f'Call `getPauseIntentValidityPeriodBlocks()`.',
            'value': self.blocks_till_pause_is_valid,
        })

        self.pause_prefix = contracts.deposit_security_module.functions.PAUSE_MESSAGE_PREFIX().call()
        logger.info({'msg': f'Call `PAUSE_MESSAGE_PREFIX()`.', 'value': self.pause_prefix})

        transports = []

        if TransportType.RABBIT in variables.MESSAGE_TRANSPORTS:
            transports.append(RabbitProvider(
                client='pauser',
                routing_keys=[MessageType.PING, MessageType.PAUSE],
                message_schema=Schema(Or(PauseMessageSchema, PingMessageSchema)),
            ))

        if TransportType.KAFKA in variables.MESSAGE_TRANSPORTS:
            transports.append(KafkaMessageProvider(
                client=f'{variables.KAFKA_GROUP_PREFIX}pause',
                message_schema=PauseMessageSchema,
            ))

        if not transports:
            logger.error({'msg': 'No transports found', 'value': variables.MESSAGE_TRANSPORTS})
            raise ValueError(f'No transports found. Provided value: {variables.MESSAGE_TRANSPORTS}')

        self.message_storage = MessageStorage(
            transports,
            filters=[
                message_metrics,
                get_pause_messages_sign_filter(self.pause_prefix),
            ],
        )

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

    def run_as_daemon(self):
        """Super-Mega infinity cycle!"""
        while True:
            self._waiting_for_new_block_and_run_cycle()

    @timeout_decorator.timeout(variables.MAX_CYCLE_LIFETIME_IN_SECONDS)
    def _waiting_for_new_block_and_run_cycle(self):
        try:
            self.run_cycle()
        except timeout_decorator.TimeoutError as exception:
            # Bot is stuck. Drop bot and restart using Docker service
            logger.error({'msg': 'Pauser bot do not respond.', 'error': str(exception)})
            raise timeout_decorator.TimeoutError('Pauser bot stuck. Restarting using docker service.') from exception
        except BlockNotFound as error:
            logger.warning({'msg': 'Fetch block exception (BlockNotFound)', 'error': str(error)})
            time.sleep(15)
        except NoActiveProviderError as exception:
            logger.error({'msg': 'No active node available.', 'error': str(exception)})
            raise NoActiveProviderError from exception
        except Exception as exception:
            logger.warning({'msg': 'Unexpected exception.', 'error': str(exception)})
            time.sleep(15)
        else:
            time.sleep(15)

    def run_cycle(self):
        logger.info({'msg': 'New pause cycle.'})
        self._update_state()

        messages = self.receive_pause_messages()

        if not messages:
            return

        staking_module_id = messages[0]['stakingModuleId']
        is_paused = contracts.staking_router.functions.getStakingModuleIsActive(staking_module_id).call(
            block_identifier=self.current_block.hash.hex(),
        )

        logger.info({
            'msg': f'Call `getStakingModuleIsActive()`.',
            'value': is_paused,
            'stakingModuleId': staking_module_id,
        })

        if is_paused:
            self.message_storage.clear()
            return

        self.pause_protocol(messages)

    def _update_state(self):
        healthcheck_pulse.pulse()

        self.current_block = fetch_latest_block(self.w3, self.current_block.number if self.current_block else 0)

    def receive_pause_messages(self) -> List[PauseMessage]:
        def validate_messages(messages: List[PauseMessage]):
            return filter(lambda msg: msg['blockNumber'] > self.current_block.number - self.blocks_till_pause_is_valid, messages)

        self.message_storage.update_messages()
        return self.message_storage.get_messages(actualize_rule=validate_messages)

    def pause_protocol(self, messages: List[PauseMessage]):
        logger.warning({'msg': 'Message pause protocol initiate.', 'value': messages})

        if not variables.ACCOUNT:
            logger.warning({'msg': 'No account provided. Skip creating tx.'})
            return

        if not variables.CREATE_TRANSACTIONS:
            logger.warning({'msg': 'Running in DRY mode.'})
            return

        for message in messages:
            if self.send_pause_transaction(message):
                break

    def send_pause_transaction(self, message: PauseMessage):
        priority_fee = self.w3.eth.max_priority_fee * 2

        logger.info({
            'msg': 'Send pause transaction.',
            'values': {
                'block_number': message['blockNumber'],
                'signature': (message['signature']['r'], compute_vs(message['signature']['v'], message['signature']['s'])),
                'priority_fee': priority_fee,
            },
        })

        pause_function = contracts.deposit_security_module.functions.pauseDeposits(
            message['blockNumber'],
            message['stakingModuleId'],
            (message['signature']['r'], compute_vs(message['signature']['v'], message['signature']['s']))
        )

        try:
            pause_function.call()
        except ContractLogicError as error:
            logger.error({'msg': 'Local transaction reverted.', 'error': str(error)})
            return False

        logger.info({'msg': 'Transaction call completed successfully.'})

        transaction = pause_function.build_transaction({
            'from': variables.ACCOUNT.address,
            'gas': variables.CONTRACT_GAS_LIMIT,
            'maxFeePerGas': self.current_block.baseFeePerGas * 2 + priority_fee,
            'maxPriorityFeePerGas': priority_fee,
            "nonce": self.w3.eth.get_transaction_count(variables.ACCOUNT.address),
        })

        signed = self.w3.eth.account.sign_transaction(transaction, variables.ACCOUNT.privateKey)

        try:
            result = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        except Exception as error:
            logger.error({'msg': 'Transaction reverted.', 'value': str(error)})
            return False
        else:
            logger.info({'msg': 'Transaction mined.', 'value': result.hex()})
            return True
