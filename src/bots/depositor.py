# pyright: reportTypedDictNotRequiredAccess=false
import logging
from collections import defaultdict
from typing import Callable, Optional

import variables
from blockchain.contracts.staking_module import StakingModuleContract
from blockchain.deposit_strategy.base_deposit_strategy import BaseDepositStrategy, MellowDepositStrategy
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from blockchain.deposit_strategy.prefered_module_to_deposit import get_preferred_to_deposit_modules
from blockchain.executor import Executor
from blockchain.typings import Web3
from metrics.metrics import (
    ACCOUNT_BALANCE,
    CURRENT_QUORUM_SIZE,
    MELLOW_VAULT_BALANCE,
    MODULE_TX_SEND,
    UNEXPECTED_EXCEPTIONS,
)
from metrics.transport_message_metrics import message_metrics_filter
from schema import Or, Schema
from transport.msg_providers.kafka import KafkaMessageProvider
from transport.msg_providers.rabbit import MessageType, RabbitProvider
from transport.msg_storage import MessageStorage
from transport.msg_types.deposit import DepositMessage, DepositMessageSchema, get_deposit_messages_sign_filter
from transport.msg_types.ping import PingMessageSchema, to_check_sum_address
from transport.types import TransportType
from web3.types import BlockData

logger = logging.getLogger(__name__)


def run_depositor(w3):
    logger.info({'msg': 'Initialize Depositor bot.'})
    gas_price_calculator = GasPriceCalculator(w3)
    sender = Sender(w3)
    mellow_deposit_strategy = MellowDepositStrategy(w3)
    base_deposit_strategy = BaseDepositStrategy(w3)
    depositor_bot = DepositorBot(w3, sender, gas_price_calculator, mellow_deposit_strategy, base_deposit_strategy)

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
    _mellow_works = True

    def __init__(
        self,
        w3: Web3,
        sender: Sender,
        gas_price_calcaulator: GasPriceCalculator,
        mellow_deposit_strategy: MellowDepositStrategy,
        base_deposit_strategy: BaseDepositStrategy,
    ):
        self.w3 = w3
        self._gas_price_calculator = gas_price_calcaulator
        self._sender = sender
        self._mellow_strategy = mellow_deposit_strategy
        self._general_strategy = base_deposit_strategy

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

    def _is_mellow_depositable(
        self,
        module_id: int
    ) -> bool:
        if not variables.MELLOW_CONTRACT_ADDRESS:
            return False
        try:
            buffered = self.w3.lido.lido.get_buffered_ether()
            unfinalized = self.w3.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth()
            if buffered < unfinalized:
                return False
            staking_module_contract: StakingModuleContract = self.w3.lido.simple_dvt_staking_strategy.staking_module_contract
            if staking_module_contract.get_staking_module_id() != module_id:
                logger.debug(
                    {
                        'msg': 'Mellow module check failed.',
                        'contract_module': staking_module_contract.get_staking_module_id(),
                        'tx_module': module_id
                    }
                )
                return False
            balance = self.w3.lido.simple_dvt_staking_strategy.vault_balance()
        except Exception as e:
            logger.warning(
                {
                    'msg': 'Failed to check if mellow depositable',
                    'module_id': module_id,
                    'err': repr(e)
                }
            )
            return False
        MELLOW_VAULT_BALANCE.labels(module_id).set(balance)
        if balance < variables.VAULT_DIRECT_DEPOSIT_THRESHOLD:
            logger.info({'msg': f'{balance} is less than VAULT_DIRECT_DEPOSIT_THRESHOLD while building mellow transaction.'})
            return False
        logger.debug({'msg': 'Mellow module check succeeded.', 'tx_module': module_id})
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

        gas_is_ok = self._gas_price_calculator.is_gas_price_ok(module_id)
        logger.info({'msg': 'Calculate gas recommendations.', 'value': gas_is_ok})

        strategy, is_mellow = self._select_strategy(module_id)
        is_deposit_amount_ok = self._gas_price_calculator.calculate_deposit_recommendation(strategy, module_id)
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': is_deposit_amount_ok})

        if is_depositable and quorum and can_deposit and gas_is_ok and is_deposit_amount_ok:
            logger.info({'msg': 'Checks passed. Prepare deposit tx.', 'is_mellow': is_mellow})
            success = self.prepare_and_send_tx(quorum, is_mellow, module_id)
            self._flashbots_works = not self._flashbots_works or success
            self._mellow_works = success
            return success

        logger.info({'msg': 'Checks failed. Skip deposit.'})
        return False

    def _select_strategy(self, module_id) -> tuple[BaseDepositStrategy, bool]:
        if self._mellow_works and self._is_mellow_depositable(module_id):
            return self._mellow_strategy, True
        return self._general_strategy, False

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

    def prepare_and_send_tx(self, quorum: list[DepositMessage], is_mellow: bool, module_id: int) -> bool:
        success = self._sender.prepare_and_send(
            quorum,
            self._flashbots_works,
            is_mellow,
        )
        logger.info({'msg': f'Tx send. Result is {success}.'})
        label = 'success' if success else 'failure'
        MODULE_TX_SEND.labels(label, module_id).inc()
        return success
