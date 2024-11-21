# pyright: reportTypedDictNotRequiredAccess=false
import logging
from collections import defaultdict
from typing import Callable, Optional

import variables
from blockchain.deposit_strategy.base_deposit_strategy import CSMDepositStrategy, DefaultDepositStrategy
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from blockchain.deposit_strategy.prefered_module_to_deposit import get_preferred_to_deposit_modules
from blockchain.deposit_strategy.strategy import DepositStrategy
from blockchain.executor import Executor
from blockchain.typings import Web3
from metrics.metrics import (
    ACCOUNT_BALANCE,
    CURRENT_QUORUM_SIZE,
    GUARDIAN_BALANCE,
    IS_DEPOSITABLE,
    MODULE_TX_SEND,
    QUORUM,
    UNEXPECTED_EXCEPTIONS,
)
from metrics.transport_message_metrics import message_metrics_filter
from schema import Or, Schema
from transport.msg_providers.onchain_transport import DepositParser, OnchainTransportProvider, PingParser
from transport.msg_providers.rabbit import MessageType, RabbitProvider
from transport.msg_storage import MessageStorage
from transport.msg_types.common import get_messages_sign_filter
from transport.msg_types.deposit import DepositMessage, DepositMessageSchema
from transport.msg_types.ping import PingMessageSchema, to_check_sum_address
from transport.types import TransportType
from web3.types import BlockData
from web3_multi_provider import FallbackProvider, MultiProvider

logger = logging.getLogger(__name__)


def run_depositor(w3):
    logger.info({'msg': 'Initialize Depositor bot.'})
    sender = Sender(w3)
    gas_price_calculator = GasPriceCalculator(w3)
    base_deposit_strategy = DefaultDepositStrategy(w3, gas_price_calculator)
    csm_strategy = CSMDepositStrategy(w3, gas_price_calculator)
    depositor_bot = DepositorBot(w3, sender, base_deposit_strategy, csm_strategy)

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

    def __init__(
        self,
        w3: Web3,
        sender: Sender,
        base_deposit_strategy: DefaultDepositStrategy,
        csm_strategy: CSMDepositStrategy,
    ):
        self.w3 = w3
        self._sender = sender
        self._general_strategy = base_deposit_strategy
        self._csm_strategy = csm_strategy

        transports = []

        if TransportType.RABBIT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                RabbitProvider(
                    routing_keys=[MessageType.PING, MessageType.DEPOSIT],
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                )
            )

        if TransportType.ONCHAIN_TRANSPORT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                OnchainTransportProvider(
                    w3=Web3(FallbackProvider(variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS)),
                    onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                    parsers_providers=[DepositParser, PingParser],
                    allowed_guardians_provider=self.w3.lido.deposit_security_module.get_guardians,
                )
            )

        if not transports:
            logger.warning({'msg': 'No transports found. Dry mode activated.', 'value': variables.MESSAGE_TRANSPORTS})

        self.message_storage = MessageStorage(
            transports,
            filters=[
                message_metrics_filter,
                to_check_sum_address,
            ],
        )

    def execute(self, block: BlockData) -> bool:
        self._check_balance()

        modules_id = get_preferred_to_deposit_modules(self.w3, variables.DEPOSIT_MODULES_WHITELIST)

        if not modules_id:
            # Read messages in case if no depositable modules for metrics
            self.message_storage.get_messages_and_actualize(lambda x: True)

        for module_id in modules_id:
            logger.info({'msg': f'Do deposit to module with id: {module_id}.'})
            try:
                self._deposit_to_module(module_id)
            except ModuleNotSupportedError as error:
                logger.warning({'msg': 'Module not supported exception.', 'error': str(error)})

        return True

    def _check_balance(self):
        eth_chain_id = self.w3.eth.chain_id

        if variables.ACCOUNT:
            balance = self.w3.eth.get_balance(variables.ACCOUNT.address)
            ACCOUNT_BALANCE.labels(variables.ACCOUNT.address, eth_chain_id).set(balance)
            logger.info({'msg': 'Check account balance.', 'value': balance})

        logger.info({'msg': 'Check guardians balances.'})

        w3_databus, w3_databus_chain_id = None, None
        if variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS:
            w3_databus = Web3(MultiProvider(variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS))
            w3_databus_chain_id = w3_databus.eth.chain_id

        guardians = self.w3.lido.deposit_security_module.get_guardians()
        for address in guardians:
            eth_balance = self.w3.eth.get_balance(address)
            GUARDIAN_BALANCE.labels(address=address, chain_id=eth_chain_id).set(eth_balance)

            if w3_databus is not None:
                balance = w3_databus.eth.get_balance(address)
                GUARDIAN_BALANCE.labels(address=address, chain_id=w3_databus_chain_id).set(balance)

    def _deposit_to_module(self, module_id: int) -> bool:
        is_depositable = self._check_module_status(module_id)
        logger.info({'msg': 'Fetch module depositable status.', 'value': is_depositable})

        quorum = self._get_quorum(module_id)
        logger.info({'msg': 'Build quorum.', 'value': quorum})

        can_deposit = self.w3.lido.deposit_security_module.can_deposit(module_id)
        logger.info({'msg': 'Can deposit to module.', 'value': can_deposit})

        strategy = self._select_strategy(module_id)
        gas_is_ok = strategy.is_gas_price_ok(module_id)
        logger.info({'msg': 'Calculate gas recommendations.', 'value': gas_is_ok})

        is_deposit_amount_ok = strategy.can_deposit_keys_based_on_ether(module_id)
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': is_deposit_amount_ok})

        if is_depositable and quorum and can_deposit and gas_is_ok and is_deposit_amount_ok:
            logger.info({'msg': 'Checks passed. Prepare deposit tx.'})
            success = self.prepare_and_send_tx(module_id, quorum)
            self._flashbots_works = not self._flashbots_works or success
            return success

        logger.info({'msg': 'Checks failed. Skip deposit.'})
        return False

    def _select_strategy(self, module_id) -> DepositStrategy:
        if module_id == 3:
            return self._csm_strategy
        return self._general_strategy

    def _check_module_status(self, module_id: int) -> bool:
        """Returns True if module is ready for deposit"""
        ready = self.w3.lido.staking_router.is_staking_module_active(module_id)
        IS_DEPOSITABLE.labels(module_id).set(int(ready))
        return ready

    def _get_quorum(self, module_id: int) -> Optional[list[DepositMessage]]:
        """Returns quorum messages or None is quorum is not ready"""
        actualize_filter = self._get_message_actualize_filter()
        prefix = self.w3.lido.deposit_security_module.get_attest_message_prefix()
        sign_filter = get_messages_sign_filter(prefix)
        messages = self.message_storage.get_messages_and_actualize(lambda x: sign_filter(x) and actualize_filter(x))

        module_filter = self._get_module_messages_filter(module_id)
        filtered_messages = list(filter(module_filter, messages))

        min_signs_to_deposit = self.w3.lido.deposit_security_module.get_guardian_quorum()

        CURRENT_QUORUM_SIZE.labels('required').set(min_signs_to_deposit)

        messages_by_block_hash = defaultdict(dict)

        max_quorum_size = 0

        for message in filtered_messages:
            # Remove duplications (blockHash, guardianAddress)
            messages_by_block_hash[message['blockHash']][message['guardianAddress']] = message

        for messages_dict in messages_by_block_hash.values():
            unified_messages = messages_dict.values()

            quorum_size = len(unified_messages)

            if quorum_size >= min_signs_to_deposit:
                CURRENT_QUORUM_SIZE.labels('current').set(quorum_size)
                QUORUM.labels(module_id).set(1)
                return list(unified_messages)

            max_quorum_size = max(quorum_size, max_quorum_size)

        CURRENT_QUORUM_SIZE.labels('current').set(max_quorum_size)
        QUORUM.labels(module_id).set(0)

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
            return message['stakingModuleId'] == module_id and message['nonce'] >= nonce

        return message_filter

    def prepare_and_send_tx(self, module_id: int, quorum: list[DepositMessage]) -> bool:
        success = self._sender.prepare_and_send(
            quorum,
            self._flashbots_works,
        )
        logger.info({'msg': f'Tx send. Result is {success}.'})
        label = 'success' if success else 'failure'
        MODULE_TX_SEND.labels(label, module_id).inc()
        return success
