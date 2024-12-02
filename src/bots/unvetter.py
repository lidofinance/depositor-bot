import logging
from typing import Callable, Optional, TypedDict

import variables
from blockchain.executor import Executor
from blockchain.typings import Web3
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from metrics.transport_message_metrics import message_metrics_filter
from schema import Or, Schema
from transport.msg_providers.onchain_transport import OnchainTransportProvider, PingParser, UnvetParser
from transport.msg_providers.rabbit import MessageType, RabbitProvider
from transport.msg_storage import MessageStorage
from transport.msg_types.common import get_messages_sign_filter
from transport.msg_types.ping import PingMessageSchema, to_check_sum_address
from transport.msg_types.unvet import UnvetMessage, UnvetMessageSchema
from transport.types import TransportType
from utils.bytes import from_hex_string_to_bytes
from web3.types import BlockData
from web3_multi_provider import FallbackProvider

logger = logging.getLogger(__name__)


def run_unvetter(w3: Web3):
    unvetter = UnvetterBot(w3)
    e = Executor(
        w3,
        unvetter.execute,
        1,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute unvetter as daemon.'})
    e.execute_as_daemon()


class UnvetterBot:
    message_storage: Optional[MessageStorage] = None

    def __init__(self, w3: Web3):
        self.w3 = w3

    def prepare_transport_bus(self):
        if self.message_storage is not None:
            return

        transports = []

        if TransportType.RABBIT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                RabbitProvider(
                    routing_keys=[MessageType.UNVET, MessageType.PING],
                    message_schema=Schema(Or(UnvetMessageSchema, PingMessageSchema)),
                )
            )

        if TransportType.ONCHAIN_TRANSPORT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                OnchainTransportProvider(
                    w3=Web3(FallbackProvider(variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS)),
                    onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
                    message_schema=Schema(Or(UnvetMessageSchema, PingMessageSchema)),
                    parsers_providers=[UnvetParser, PingParser],
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
            ],
        )

    def execute(self, block: BlockData) -> bool:
        if self.w3.lido.deposit_security_module.version() == 1:
            logger.warning({'msg': 'DSM version is not supported.'})
            return True

        self.prepare_transport_bus()
        messages = self.receive_unvet_messages()
        logger.info({'msg': f'Received {len(messages)} unvet messages.'})

        for message in messages:
            self._send_unvet_message(message)

        return True

    def receive_unvet_messages(self) -> list[UnvetMessage]:
        if self.message_storage is None:
            return []

        actualize_filter = self._get_message_actualize_filter()
        prefix = self.w3.lido.deposit_security_module.get_unvet_message_prefix()
        sign_filter = get_messages_sign_filter(prefix)
        return self.message_storage.get_messages_and_actualize(lambda x: sign_filter(x) and actualize_filter(x))

    def _get_message_actualize_filter(self) -> Callable[[UnvetMessage], bool]:
        modules = self.w3.lido.staking_router.get_staking_module_ids()

        nonces = {}
        for module_id in modules:
            nonces[module_id] = self.w3.lido.staking_router.get_staking_module_nonce(module_id)

        guardians_list = self.w3.lido.deposit_security_module.get_guardians()

        def message_filter(message: UnvetMessage) -> bool:
            if message['guardianAddress'] not in guardians_list:
                UNEXPECTED_EXCEPTIONS.labels('unexpected_guardian_address').inc()
                return False

            # If message nonce is lower than in module, message is invalid
            # If higher, maybe unvetter node is outdated -> message can be valid
            return message['nonce'] >= nonces[message['stakingModuleId']]

        return message_filter

    def _send_unvet_message(self, message: UnvetMessage) -> bool:
        module_id = message['stakingModuleId']

        logger.warning({'msg': f'Handle unvet message for module: {module_id}', 'value': message})

        actual_nonce = self.w3.lido.staking_router.get_staking_module_nonce(module_id)

        self._clear_outdated_messages_for_module(module_id, actual_nonce)

        operator_ids = from_hex_string_to_bytes(message['operatorIds'])
        max_operators_per_unvetting = self.w3.lido.deposit_security_module.get_max_operators_per_unvetting()
        node_operators_count = len(operator_ids) / 8
        if node_operators_count > max_operators_per_unvetting:
            logger.error(
                {
                    'msg': 'max_operators_per_unvetting check failed.',
                    'node_operators_count': node_operators_count,
                    'max_operators_per_unvetting': max_operators_per_unvetting,
                }
            )
            return False

        unvet_tx = self.w3.lido.deposit_security_module.unvet_signing_keys(
            message['blockNumber'],
            message['blockHash'],
            module_id,
            message['nonce'],
            from_hex_string_to_bytes(message['operatorIds']),
            from_hex_string_to_bytes(message['vettedKeysByOperator']),
            (message['signature']['r'], message['signature']['_vs']),
        )

        if not self.w3.transaction.check(unvet_tx):
            return False

        result = self.w3.transaction.send(unvet_tx, False, 6)
        logger.info({'msg': f'Transaction send. Result is {result}.', 'value': result})
        return result

    def _clear_outdated_messages_for_module(self, module_id: int, nonce: int):
        prefix = self.w3.lido.deposit_security_module.get_unvet_message_prefix()
        is_message_signed_filter = get_messages_sign_filter(prefix)

        def is_unvet_message_relevant(msg: TypedDict) -> bool:
            is_message_relevant = msg['stakingModuleId'] != module_id or int(msg['nonce']) >= nonce
            return is_message_relevant and is_message_signed_filter(msg)

        self.message_storage.get_messages_and_actualize(is_unvet_message_relevant)
