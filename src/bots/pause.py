import logging
from typing import Callable

from schema import Schema, Or
from web3.types import BlockData

import variables
from blockchain.typings import Web3
from cryptography.verify_signature import compute_vs
from metrics.transport_message_metrics import message_metrics_filter
from transport.msg_providers.kafka import KafkaMessageProvider
from transport.msg_providers.rabbit import RabbitProvider, MessageType
from transport.msg_schemas import PauseMessageSchema, get_pause_messages_sign_filter, PauseMessage, PingMessageSchema
from transport.msg_storage import MessageStorage
from transport.types import TransportType


logger = logging.getLogger(__name__)


class PauserBot:
    def __init__(self, w3: Web3):
        self.w3 = w3

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
                message_schema=Schema(Or(PauseMessageSchema, PingMessageSchema)),
            ))

        if not transports:
            logger.warning({'msg': 'No transports found', 'value': variables.MESSAGE_TRANSPORTS})

        pause_prefix = self.w3.lido.deposit_security_module.get_pause_message_prefix()

        self.message_storage = MessageStorage(
            transports,
            filters=[
                message_metrics_filter,
                get_pause_messages_sign_filter(pause_prefix),
            ],
        )

    def execute(self, block: BlockData) -> bool:
        messages = self.receive_pause_messages()
        logger.info({'msg': f'Received {len(messages)} pause messages.'})

        for message in messages:
            self._send_pause_message(message)

        return True

    def receive_pause_messages(self) -> list[PauseMessage]:
        actualize_filter = self._get_message_actualize_filter()
        return self.message_storage.get_messages(actualize_filter)

    def _get_message_actualize_filter(self) -> Callable[[PauseMessage], bool]:
        current_block = self.w3.eth.get_block('latest')
        message_validity_time = self.w3.lido.deposit_security_module.get_pause_intent_validity_period_blocks()

        def message_filter(message: PauseMessage) -> bool:
            # TODO Metrics for filtered messages
            return message['blockNumber'] > current_block['number'] - message_validity_time

        return message_filter

    def _send_pause_message(self, message: PauseMessage) -> bool:
        module_id = message['stakingModuleId']

        logger.warning({'msg': f'Handle pause message for module: {module_id}', 'value': message})

        if not self.w3.lido.staking_router.is_staking_module_active(module_id):
            # Module already deactivated
            self._clear_outdated_messages_for_module(module_id)
            logger.info({'msg': f'Module {module_id} already paused. Skip message.'})
            return False

        pause_tx = self.w3.lido.deposit_security_module.pause_deposits(
            message['blockNumber'],
            module_id,
            (message['signature']['r'], compute_vs(message['signature']['v'], message['signature']['s']))
        )

        result = self.w3.transaction.send(pause_tx, False, 6)
        logger.info({'msg': f'Transaction send. Result is {result}.', 'value': result})
        return result

    def _clear_outdated_messages_for_module(self, module_id: int) -> None:
        self.message_storage.get_messages(lambda message: message['stakingModuleId'] != module_id)
