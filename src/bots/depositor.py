# pyright: reportTypedDictNotRequiredAccess=false
import logging
from collections import defaultdict
from typing import Callable, Optional

import variables
from blockchain.contracts.staking_module import StakingModuleContract
from blockchain.deposit_strategy.curated_module import CuratedModuleDepositStrategy
from blockchain.deposit_strategy.interface import ModuleDepositStrategyInterface
from blockchain.deposit_strategy.prefered_module_to_deposit import get_preferred_to_deposit_modules
from blockchain.executor import Executor
from blockchain.typings import Web3
from cryptography.verify_signature import compute_vs
from eth_typing import Hash32, ChecksumAddress
from metrics.metrics import (
    ACCOUNT_BALANCE,
    CURRENT_QUORUM_SIZE,
    UNEXPECTED_EXCEPTIONS,
    MELLOW_VAULT_BALANCE,
)
from metrics.transport_message_metrics import message_metrics_filter
from schema import Or, Schema
from transport.msg_providers.kafka import KafkaMessageProvider
from transport.msg_providers.rabbit import MessageType, RabbitProvider
from transport.msg_storage import MessageStorage
from transport.msg_types.deposit import DepositMessage, DepositMessageSchema, get_deposit_messages_sign_filter
from transport.msg_types.ping import PingMessageSchema, to_check_sum_address
from transport.types import TransportType
from web3.contract.contract import ContractFunction
from web3.types import BlockData

logger = logging.getLogger(__name__)


def run_depositor(w3):
    logger.info({'msg': 'Initialize Depositor bot.'})
    depositor_bot = DepositorBot(w3)

    e = Executor(
        w3,
        depositor_bot.execute,
        1,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute depositor as daemon.'})
    e.execute_as_daemon()


class ModuleNotSupportedError(Exception):
    pass


class DepositorBot:
    _flashbots_works = True

    def __init__(self, w3: Web3):
        self.w3 = w3

        transports = []

        if TransportType.RABBIT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                RabbitProvider(
                    client='depositor',
                    routing_keys=[MessageType.PING, MessageType.DEPOSIT],
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                )
            )

        if TransportType.KAFKA in variables.MESSAGE_TRANSPORTS:
            transports.append(
                KafkaMessageProvider(
                    client=f'{variables.KAFKA_GROUP_PREFIX}deposit',
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                )
            )

        if not transports:
            logger.warning({'msg': 'No transports found. Dry mode activated.', 'value': variables.MESSAGE_TRANSPORTS})

        self.message_storage = MessageStorage(
            transports,
            filters=[
                message_metrics_filter,
                to_check_sum_address,
                get_deposit_messages_sign_filter(self.w3),
            ],
        )

    def execute(self, block: BlockData) -> bool:
        self._check_balance()

        modules_id = get_preferred_to_deposit_modules(self.w3, variables.DEPOSIT_MODULES_WHITELIST)

        if not modules_id:
            # Read messages in case if no depositable modules for metrics
            self.message_storage.receive_messages()

        for module_id in modules_id:
            logger.info({'msg': f'Do deposit to module with id: {module_id}.'})
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

        can_deposit = self.w3.lido.deposit_security_module.can_deposit(module_id)
        logger.info({'msg': 'Can deposit to module.', 'value': can_deposit})

        module_strategy = self._get_module_strategy(module_id)

        gas_is_ok = module_strategy.is_gas_price_ok()
        logger.info({'msg': 'Calculate gas recommendations.', 'value': gas_is_ok})

        keys_amount_is_profitable = module_strategy.is_deposited_keys_amount_ok()
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': keys_amount_is_profitable})

        if is_depositable and quorum and can_deposit and gas_is_ok and keys_amount_is_profitable:
            logger.info({'msg': 'Checks passed. Prepare deposit tx.'})
            return self._build_and_send_deposit_tx(quorum)

        logger.info({'msg': 'Checks failed. Skip deposit.'})
        return False

    def _get_module_strategy(self, module_id: int) -> ModuleDepositStrategyInterface:
        if module_id in (1, 2, 3):
            return CuratedModuleDepositStrategy(self.w3, module_id)

        raise ModuleNotSupportedError(f'Module with id: {module_id} is not supported yet.')

    def _check_module_status(self, module_id: int) -> bool:
        """Returns True if module is ready for deposit"""
        return self.w3.lido.staking_router.is_staking_module_active(module_id)

    def _get_quorum(self, module_id: int) -> Optional[list[DepositMessage]]:
        """Returns quorum messages or None is quorum is not ready"""
        actualize_filter = self._get_message_actualize_filter()
        messages = self.message_storage.get_messages(actualize_filter)

        module_filter = self._get_module_messages_filter(module_id)
        messages = list(filter(module_filter, messages))

        min_signs_to_deposit = self.w3.lido.deposit_security_module.get_guardian_quorum()

        CURRENT_QUORUM_SIZE.labels('required').set(min_signs_to_deposit)

        messages_by_block_hash = defaultdict(dict)

        max_quorum_size = 0

        for message in messages:
            # Remove duplications (blockHash, guardianAddress)
            messages_by_block_hash[message['blockHash']][message['guardianAddress']] = message

        for messages_dict in messages_by_block_hash.values():
            unified_messages = messages_dict.values()

            quorum_size = len(unified_messages)

            if quorum_size >= min_signs_to_deposit:
                CURRENT_QUORUM_SIZE.labels('current').set(quorum_size)
                return list(unified_messages)

            max_quorum_size = max(quorum_size, max_quorum_size)

        CURRENT_QUORUM_SIZE.labels('current').set(max_quorum_size)

    def _get_message_actualize_filter(self) -> Callable[[DepositMessage], bool]:
        latest = self.w3.eth.get_block('latest')
        deposit_root = '0x' + self.w3.lido.deposit_contract.get_deposit_root().hex()
        guardians_list = self.w3.lido.deposit_security_module.get_guardians()

        def message_filter(message: DepositMessage) -> bool:
            if message['guardianAddress'] not in guardians_list:
                UNEXPECTED_EXCEPTIONS.labels('unexpected_guardian_address').inc()
                return False

            if message['blockNumber'] < latest['number'] - 200:
                return False

            # Message from council is newer than depositor node latest block
            if message['blockNumber'] > latest['number']:
                # can't be verified, so skip
                return True

            if message['depositRoot'] != deposit_root:
                return False

            return True

        return message_filter

    def _get_module_messages_filter(self, module_id: int) -> Callable[[DepositMessage], bool]:
        nonce = self.w3.lido.staking_router.get_staking_module_nonce(module_id)

        def message_filter(message: DepositMessage) -> bool:
            if message['stakingModuleId'] != module_id:
                return False

            if message['nonce'] < nonce:
                return False

            return True

        return message_filter

    def _build_and_send_deposit_tx(self, quorum: list[DepositMessage]) -> bool:
        signs = self._prepare_signs_for_deposit(quorum)

        return self._send_deposit_tx(
            quorum[0]['blockNumber'],
            Hash32(bytes.fromhex(quorum[0]['blockHash'][2:])),
            Hash32(bytes.fromhex(quorum[0]['depositRoot'][2:])),
            quorum[0]['stakingModuleId'],
            quorum[0]['nonce'],
            b'',
            signs,
        )

    @staticmethod
    def _prepare_signs_for_deposit(quorum: list[DepositMessage]) -> tuple[tuple[str, str], ...]:
        sorted_messages = sorted(quorum, key=lambda msg: int(msg['guardianAddress'], 16))

        return tuple((msg['signature']['r'], compute_vs(msg['signature']['v'], msg['signature']['s'])) for msg in sorted_messages)

    def _send_deposit_tx(
        self,
        block_number: int,
        block_hash: Hash32,
        deposit_root: Hash32,
        staking_module_id: int,
        staking_module_nonce: int,
        payload: bytes,
        guardian_signs: tuple[tuple[str, str], ...],
    ) -> bool:
        """Returns transactions success status"""
        # Prepare transaction and send
        success = self._send_mellow_tx(
            block_number,
            block_hash,
            deposit_root,
            staking_module_id,
            staking_module_nonce,
            payload,
            guardian_signs,
        )
        if not success:
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

        self._flashbots_works = not self._flashbots_works or success
        return success

    def _is_mellow_depositable(
        self,
        vault_address: ChecksumAddress,
        module_id: int
    ) -> bool:
        staking_module_contract: StakingModuleContract = self.w3.lido.simple_dvt_staking_strategy.staking_module_contract
        if staking_module_contract.get_staking_module_id() != module_id:
            logger.debug({'msg': 'While building mellow transaction module check failed.',
                          'contract_module': staking_module_contract.get_staking_module_id(),
                          'tx_module': module_id})
            return False
        balance = staking_module_contract.weth_contract.balance_of(vault_address)
        MELLOW_VAULT_BALANCE.labels(module_id).set(balance)
        if balance < variables.VAULT_DIRECT_DEPOSIT_THRESHOLD:
            logger.debug({'msg': f'{balance} is less than VAULT_DIRECT_DEPOSIT_THRESHOLD while building mellow transaction.'})
            return False
        return True

    def _build_transaction_mellow(
        self,
        block_number: int,
        block_hash: Hash32,
        deposit_root: Hash32,
        staking_module_id: int,
        staking_module_nonce: int,
        payload: bytes,
        guardian_signs: tuple[tuple[str, str], ...],
    ) -> Optional[ContractFunction]:
        """
        It either follows a regular flow or builds a direct deposit transaction.

        Conditions to build direct deposit transaction are:
        1. Env variable MELLOW_CONTRACT_ADDRESS is set
        2. balance in the vault >= VAULT_DIRECT_DEPOSIT_THRESHOLD
        3. The calls responded without errors
        """
        if not variables.MELLOW_CONTRACT_ADDRESS:
            return None

        vault_address = self.w3.lido.simple_dvt_staking_strategy.vault()
        if not self._is_mellow_depositable(vault_address, staking_module_id):
            return None

        return self.w3.lido.simple_dvt_staking_strategy.convert_and_deposit(
            block_number,
            block_hash,
            deposit_root,
            staking_module_nonce,
            payload,
            guardian_signs
        )

    def _send_mellow_tx(
        self,
        block_number: int,
        block_hash: Hash32,
        deposit_root: Hash32,
        staking_module_id: int,
        staking_module_nonce: int,
        payload: bytes,
        guardian_signs: tuple[tuple[str, str], ...],
    ) -> bool:
        if not variables.MELLOW_CONTRACT_ADDRESS:
            return False

        try:
            mellow_tx = self._build_transaction_mellow(
                block_number,
                block_hash,
                deposit_root,
                staking_module_id,
                staking_module_nonce,
                payload,
                guardian_signs,
            )
            if mellow_tx is None:
                return False
            if not self.w3.transaction.check(mellow_tx):
                return False

            logger.info({'msg': 'Send mellow deposit transaction.', 'with_flashbots': self._flashbots_works})
            return self.w3.transaction.send(mellow_tx, self._flashbots_works, 6)
        except Exception as e:
            logger.info({'msg': 'Error while sending the mellow transaction', 'error': str(e)})
            return False
