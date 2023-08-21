import logging
from collections import defaultdict
from typing import Optional, Callable

from eth_typing import Hash32
from schema import Or, Schema
from web3.types import BlockData

import variables

from blockchain.deposit_strategy.curated_module import CuratedModuleDepositStrategy
from blockchain.deposit_strategy.interface import ModuleDepositStrategyInterface
from blockchain.typings import Web3
from cryptography.verify_signature import compute_vs
from metrics.metrics import (
    ACCOUNT_BALANCE, CURRENT_QUORUM_SIZE,
)
from metrics.transport_message_metrics import message_metrics_filter
from transport.msg_providers.kafka import KafkaMessageProvider
from transport.msg_providers.rabbit import RabbitProvider, MessageType
from transport.msg_schemas import (
    DepositMessageSchema,
    PingMessageSchema,
    get_deposit_messages_sign_filter,
    DepositMessage,
)
from transport.msg_storage import MessageStorage
from transport.types import TransportType


logger = logging.getLogger(__name__)


class ModuleNotSupportedError(Exception):
    pass


class DepositorBot:
    _flashbots_works = True

    def __init__(self, w3: Web3):
        self.w3 = w3

        transports = []

        if TransportType.RABBIT in variables.MESSAGE_TRANSPORTS:
            transports.append(RabbitProvider(
                client='depositor',
                routing_keys=[MessageType.PING, MessageType.DEPOSIT],
                message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
            ))

        if TransportType.KAFKA in variables.MESSAGE_TRANSPORTS:
            transports.append(KafkaMessageProvider(
                client=f'{variables.KAFKA_GROUP_PREFIX}deposit',
                message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
            ))

        if not transports:
            logger.warning({'msg': 'No transports found. Dry mode activated.', 'value': variables.MESSAGE_TRANSPORTS})

        attest_prefix = self.w3.lido.deposit_security_module.get_attest_message_prefix()

        self.message_storage = MessageStorage(
            transports,
            filters=[
                message_metrics_filter,
                get_deposit_messages_sign_filter(attest_prefix),
            ],
        )

    def execute(self, block: BlockData) -> bool:
        self._check_balance()

        module_ids = self.w3.lido.staking_router.get_staking_module_ids()

        for module_id in module_ids:
            logger.info({'msg': f'Do deposit for module with id: {module_id}.'})
            try:
                self._deposit_to_module(module_id)
            except ModuleNotSupportedError as error:
                logger.warning({'msg': 'Module not supported exception.', 'error': str(error)})

        return True

    def _check_balance(self):
        if variables.ACCOUNT:
            balance = self.w3.eth.get_balance(variables.ACCOUNT.address)
            ACCOUNT_BALANCE.set(balance)
            logger.info({'msg': 'Check account balance.', 'value': balance})
        else:
            logger.info({'msg': 'No account provided. Dry mode.'})
            ACCOUNT_BALANCE.set(0)

    def _deposit_to_module(self, module_id: int) -> bool:
        is_depositable = self._check_module_status(module_id)
        logger.info({'msg': 'Fetch module depositable status.', 'value': is_depositable})

        quorum = self._get_quorum(module_id)
        logger.info({'msg': 'Build quorum.', 'value': quorum})

        module_strategy = self._get_module_strategy(module_id)

        gas_is_ok = module_strategy.is_gas_price_ok()
        logger.info({'msg': 'Calculate gas recommendations.', 'value': gas_is_ok})

        keys_amount_is_profitable = module_strategy.is_deposited_keys_amount_ok()
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': keys_amount_is_profitable})

        if is_depositable and quorum and gas_is_ok and keys_amount_is_profitable:
            logger.info({'msg': 'Checks passed. Prepare deposit tx.'})
            return self._build_and_send_deposit_tx(quorum)

        logger.info({'msg': 'Checks failed. Skip deposit.'})
        return False

    def _get_module_strategy(self, module_id: int) -> ModuleDepositStrategyInterface:
        # ToDo somehow support different gas strategies for different module types
        if module_id == 1:
            return CuratedModuleDepositStrategy(self.w3, module_id)

        raise ModuleNotSupportedError(f'Module with id: {module_id} is not supported yet.')

    def _check_module_status(self, module_id: int) -> bool:
        """Returns True if module is ready for deposit"""
        is_active = self.w3.lido.staking_router.is_staking_module_active(module_id)
        is_deposits_paused = self.w3.lido.staking_router.is_staking_module_deposits_paused(module_id)
        return is_active and not is_deposits_paused

    def _get_quorum(self, module_id: int) -> Optional[list[DepositMessage]]:
        """Returns quorum messages or None is quorum is not ready"""
        actualize_filter = self._get_message_actualize_filter(module_id)
        messages = self.message_storage.get_messages(actualize_filter)
        min_signs_to_deposit = self.w3.lido.deposit_security_module.get_guardian_quorum()

        messages_by_block_hash = defaultdict(dict)

        max_quorum_size = 0

        for message in messages:
            # Remove duplications (blockHash, guardianAddress)
            messages_by_block_hash[message['blockHash']][message['guardianAddress']] = message

        for messages_dict in messages_by_block_hash.values():
            unified_messages = messages_dict.values()

            quorum_size = len(unified_messages)

            if quorum_size >= min_signs_to_deposit:
                CURRENT_QUORUM_SIZE.set(quorum_size)
                return list(unified_messages)

            max_quorum_size = max(quorum_size, max_quorum_size)

        CURRENT_QUORUM_SIZE.set(max_quorum_size)

    def _get_message_actualize_filter(self, module_id: int) -> Callable[[DepositMessage], bool]:
        latest = self.w3.eth.get_block('latest')

        deposit_root = '0x' + self.w3.lido.deposit_contract.get_deposit_root().hex()
        nonce = self.w3.lido.staking_router.get_staking_module_nonce(module_id)
        guardians_list = self.w3.lido.deposit_security_module.get_guardians()

        def message_filter(message: DepositMessage) -> bool:
            if message['guardianAddress'] not in guardians_list:
                return False

            if message['blockNumber'] < latest['number'] - 200:
                return False

            # Message from council is newer than depositor node latest block
            if message['blockNumber'] > latest['number']:
                # can't be verified, so skip
                return True

            if message['nonce'] != nonce:
                return False

            if message['depositRoot'] != deposit_root:
                return False

            return True

        return message_filter

    def _build_and_send_deposit_tx(self, quorum: list[DepositMessage]) -> bool:
        signs = self._prepare_signs_for_deposit(quorum)

        return self._send_deposit_tx(
            quorum[0]['blockNumber'],
            quorum[0]['blockHash'],
            quorum[0]['depositRoot'],
            quorum[0]['stakingModuleId'],
            quorum[0]['nonce'],
            b'',
            signs,
        )

    @staticmethod
    def _prepare_signs_for_deposit(quorum: list[DepositMessage]) -> list[tuple[str, str]]:
        sorted_messages = sorted(quorum, key=lambda msg: int(msg['guardianAddress'], 16))

        return [
            (msg['signature']['r'], compute_vs(msg['signature']['v'], msg['signature']['s']))
            for msg in sorted_messages
        ]

    def _send_deposit_tx(
        self,
        block_number: int,
        block_hash: Hash32,
        deposit_root: Hash32,
        staking_module_id: int,
        staking_module_nonce: int,
        payload: bytes,
        guardian_signs: list[tuple[str, str]]
    ) -> bool:
        """Returns transactions success status"""
        # Prepare transaction and send
        deposit_tx = self.w3.lido.deposit_security_module.deposit_buffered_ether(
            block_number,
            block_hash,
            deposit_root,
            staking_module_id,
            staking_module_nonce,
            payload,
            guardian_signs,
        )

        if not self.w3.transaction.check(deposit_tx):
            return False

        logger.info({'msg': 'Send deposit transaction.', 'with_flashbots': self._flashbots_works})
        success = self.w3.transaction.send(deposit_tx, self._flashbots_works, 6)

        logger.info({'msg': f'Tx send. Result is {success}.'})

        if self._flashbots_works and not success:
            self._flashbots_works = False
        else:
            self._flashbots_works = True

        return success
