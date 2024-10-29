# pyright: reportTypedDictNotRequiredAccess=false

import logging
from typing import Callable

import variables
from blockchain.executor import Executor
from blockchain.typings import Web3
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from metrics.transport_message_metrics import message_metrics_filter
from schema import Or, Schema
from transport.msg_providers.onchain_transport import OnchainTransportProvider, PauseV2Parser, PauseV3Parser, PingParser
from transport.msg_providers.rabbit import MessageType, RabbitProvider
from transport.msg_storage import MessageStorage
from transport.msg_types.common import get_messages_sign_filter
from transport.msg_types.pause import PauseMessage, PauseMessageSchema
from transport.msg_types.ping import PingMessageSchema, to_check_sum_address
from transport.types import TransportType
from web3.types import BlockData
from web3_multi_provider import FallbackProvider

logger = logging.getLogger(__name__)


def run_pauser(w3: Web3):
    pause = PauserBot(w3)
    e = Executor(
        w3,
        pause.execute,
        1,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute pauser as daemon.'})
    e.execute_as_daemon()


class PauserBot:
    def __init__(self, w3: Web3):
        self.w3 = w3

        transports = []

        if TransportType.RABBIT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                RabbitProvider(
                    routing_keys=[MessageType.PING, MessageType.PAUSE],
                    message_schema=Schema(Or(PauseMessageSchema, PingMessageSchema)),
                )
            )

        if TransportType.ONCHAIN_TRANSPORT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                OnchainTransportProvider(
                    w3=Web3(FallbackProvider(variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS)),
                    onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
                    message_schema=Schema(Or(PauseMessageSchema, PingMessageSchema)),
                    parsers_providers=[PauseV2Parser, PauseV3Parser, PingParser],
                    allowed_guardians_provider=self.w3.lido.deposit_security_module.get_guardians,
                )
            )

        if not transports:
            logger.warning({'msg': 'No transports found', 'value': variables.MESSAGE_TRANSPORTS})

        self.message_storage = MessageStorage(
            transports,
            filters=[
                message_metrics_filter,
                to_check_sum_address,
                get_messages_sign_filter(self.w3),
            ],
        )

    def execute(self, block: BlockData) -> bool:
        messages = self.receive_pause_messages()
        logger.info({'msg': f'Received {len(messages)} pause messages.'})

        for message in messages:
            return self._send_pause_v2(message)

        return True

    def receive_pause_messages(self) -> list[PauseMessage]:
        actualize_filter = self._get_message_actualize_filter()
        return self.message_storage.get_messages(actualize_filter)

    def _get_message_actualize_filter(self) -> Callable[[PauseMessage], bool]:
        current_block = self.w3.eth.get_block('latest')
        message_validity_time = self.w3.lido.deposit_security_module.get_pause_intent_validity_period_blocks()
        guardians_list = self.w3.lido.deposit_security_module.get_guardians()

        def message_filter(message: PauseMessage) -> bool:
            if message['guardianAddress'] not in guardians_list:
                UNEXPECTED_EXCEPTIONS.labels('unexpected_guardian_address').inc()
                return False

            return message['blockNumber'] > current_block['number'] - message_validity_time

        return message_filter

    def _send_pause_v2(self, message: PauseMessage):
        if self.w3.lido.deposit_security_module.is_deposits_paused():
            logger.info({'msg': 'Lido deposits already paused. Skip message.'})
            self.message_storage.clear()
            return False

        pause_tx = self.w3.lido.deposit_security_module.pause_deposits_v2(
            message['blockNumber'], (message['signature']['r'], message['signature']['_vs'])
        )

        result = self.w3.transaction.send(pause_tx, False, 6)
        logger.info({'msg': f'Transaction send. Result is {result}.', 'value': result})
        return result

    def _clear_outdated_messages_for_module(self, module_id: int) -> None:
        self.message_storage.get_messages(lambda message: message['stakingModuleId'] != module_id)
