# pyright: reportTypedDictNotRequiredAccess=false
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import variables
from blockchain.deposit_strategy.base_deposit_strategy import CSMDepositStrategy, DefaultDepositStrategy
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from blockchain.deposit_strategy.strategy import DepositStrategy
from blockchain.executor import Executor
from blockchain.typings import Web3
from metrics.metrics import (
    ACCOUNT_BALANCE,
    CURRENT_QUORUM_SIZE,
    GUARDIAN_BALANCE,
    MODULE_TX_SEND,
    QUORUM,
    UNEXPECTED_EXCEPTIONS,
)
from metrics.transport_message_metrics import message_metrics_filter
from schema import Or, Schema
from transport.msg_providers.onchain_transport import DepositParser, OnchainTransportProvider, PingParser
from transport.msg_providers.rabbit import MessageType, RabbitProvider
from transport.msg_storage import MessageStorage
from transport.msg_types.common import BotMessage, get_messages_sign_filter
from transport.msg_types.deposit import DepositMessage, DepositMessageSchema
from transport.msg_types.ping import PingMessageSchema, to_check_sum_address
from transport.types import TransportType
from web3.types import BlockData

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
        now = datetime.now()
        self._module_last_heart_beat: Dict[int, datetime] = {module_id: now for module_id in variables.DEPOSIT_MODULES_WHITELIST}

        transports = []

        if TransportType.RABBIT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                RabbitProvider(
                    routing_keys=[MessageType.PING, MessageType.DEPOSIT],
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                )
            )

        self._onchain_transport_w3 = None
        if TransportType.ONCHAIN_TRANSPORT in variables.MESSAGE_TRANSPORTS:
            self._onchain_transport_w3 = OnchainTransportProvider.create_onchain_transport_w3()
            transports.append(
                OnchainTransportProvider(
                    w3=self._onchain_transport_w3,
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

        for module_id in self._get_preferred_to_deposit_modules():
            logger.info({'msg': f'Do deposit to module with id: {module_id}.'})
            try:
                self._deposit_to_module(module_id)
            except ModuleNotSupportedError as error:
                logger.warning({'msg': 'Module not supported exception.', 'error': str(error)})

        return True

    def _check_balance(self):
        if variables.ACCOUNT:
            balance = self.w3.eth.get_balance(variables.ACCOUNT.address)
            ACCOUNT_BALANCE.labels(variables.ACCOUNT.address, self.w3.eth.chain_id).set(balance)
            logger.info({'msg': 'Check account balance.', 'value': balance})

        logger.info({'msg': 'Check guardians balances.'})

        guardians = self.w3.lido.deposit_security_module.get_guardians()
        providers = [self.w3]
        if self._onchain_transport_w3 is not None:
            providers.append(self._onchain_transport_w3)
        for address in guardians:
            for provider in providers:
                balance = self.w3.eth.get_balance(address)
                GUARDIAN_BALANCE.labels(address=address, chain_id=provider.eth.chain_id).set(balance)

    def _deposit_to_module(self, module_id: int) -> bool:
        can_deposit = self.w3.lido.deposit_security_module.can_deposit(module_id)
        logger.info({'msg': 'Can deposit to module.', 'value': can_deposit})

        quorum = self._get_quorum(module_id)
        logger.info({'msg': 'Build quorum.', 'value': quorum})

        strategy = self._select_strategy(module_id)
        gas_is_ok = strategy.is_gas_price_ok(module_id)
        logger.info({'msg': 'Calculate gas recommendations.', 'value': gas_is_ok})

        is_deposit_amount_ok = strategy.can_deposit_keys_based_on_ether(module_id)
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': is_deposit_amount_ok})

        if can_deposit and quorum and gas_is_ok and is_deposit_amount_ok:
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

    def _get_quorum(self, module_id: int) -> Optional[List[DepositMessage]]:
        """
        Returns quorum messages or None if the quorum is not ready.
        """
        # Fetch messages and apply filters
        messages = self._fetch_actual_messages()

        # Apply module-specific filtering
        module_filter = self._get_module_messages_filter(module_id)
        filtered_messages = list(filter(module_filter, messages))

        # Get the required quorum size
        min_signs_to_deposit = self.w3.lido.deposit_security_module.get_guardian_quorum()
        CURRENT_QUORUM_SIZE.labels('required').set(min_signs_to_deposit)

        # Group messages by block hash and guardian address
        messages_by_block_hash = defaultdict(dict)
        for message in filtered_messages:
            messages_by_block_hash[message['blockHash']][message['guardianAddress']] = message

        # Evaluate quorum for each block hash
        max_quorum_size = 0
        for guardian_messages in messages_by_block_hash.values():
            unified_messages = list(guardian_messages.values())
            quorum_size = len(unified_messages)

            if quorum_size >= min_signs_to_deposit:
                # Cache and return the quorum
                CURRENT_QUORUM_SIZE.labels('current').set(quorum_size)
                QUORUM.labels(module_id).set(1)
                return unified_messages

            # Track the largest quorum size seen
            max_quorum_size = max(quorum_size, max_quorum_size)

        # Update metrics and indicate no quorum
        CURRENT_QUORUM_SIZE.labels('current').set(max_quorum_size)
        QUORUM.labels(module_id).set(0)
        return None

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
        return lambda message: message['stakingModuleId'] == module_id and message['nonce'] >= nonce

    def prepare_and_send_tx(self, module_id: int, quorum: list[DepositMessage]) -> bool:
        success = self._sender.prepare_and_send(
            quorum,
            self._flashbots_works,
        )
        logger.info({'msg': f'Tx send. Result is {success}.'})
        label = 'success' if success else 'failure'
        MODULE_TX_SEND.labels(label, module_id).inc()
        return success

    def _fetch_actual_messages(self) -> list[BotMessage]:
        # Fetch messages and apply filters
        actualize_filter = self._get_message_actualize_filter()
        prefix = self.w3.lido.deposit_security_module.get_attest_message_prefix()
        sign_filter = get_messages_sign_filter(prefix)

        return self.message_storage.get_messages_and_actualize(lambda x: sign_filter(x) and actualize_filter(x))

    def _get_preferred_to_deposit_modules(self) -> list[int]:
        # gather quorum
        now = datetime.now()
        for module_id in variables.DEPOSIT_MODULES_WHITELIST:
            if self._get_quorum(module_id):
                self._module_last_heart_beat[module_id] = now

        # filter out non allow-listed modules
        module_ids = [
            module_id
            for module_id in self.w3.lido.staking_router.get_staking_module_ids()
            if module_id in variables.DEPOSIT_MODULES_WHITELIST
        ]
        # get digests for all the modules
        module_digests = self.w3.lido.staking_router.get_staking_module_digests(module_ids)
        # sort modules by validator count
        sorted_module_digests = sorted(
            module_digests,
            key=lambda module_digest: self.get_active_validators_count(module_digest),
        )
        # decide if modules are healthy
        # module[2][0] - module_id
        modules_healthiness = [(module[2][0], self._is_module_healthy(module[2][0])) for module in sorted_module_digests]

        # take all the modules in sorted order until the first healthy one(including)
        result = self._take_until_first_healthy_module(modules_healthiness)
        logger.info({'msg': f'Module iteration order {result}.'})
        return result

    def _is_module_healthy(self, module_id: int) -> bool:
        # Check if the quorum cache is valid
        last_quorum_time = self._module_last_heart_beat[module_id]
        is_valid_quorum = (datetime.now() - last_quorum_time) <= timedelta(minutes=variables.QUORUM_RETENTION_MINUTES)
        logger.info({'msg': f'Is valid quorum {is_valid_quorum}.', 'module_id': module_id})

        # Check if module is available for deposits
        can_deposit = self.w3.lido.deposit_security_module.can_deposit(module_id)
        logger.info({'msg': f'Can deposit {can_deposit}.', 'module_id': module_id})

        strategy = self._select_strategy(module_id)
        return can_deposit and is_valid_quorum and strategy.deposited_keys_amount(module_id) >= 1

    @staticmethod
    def get_active_validators_count(module: list) -> int:
        total_deposited = module[3][1]  # totalDepositedValidators
        total_exited = module[3][0]  # totalExitedValidators
        return total_deposited - total_exited

    @staticmethod
    def _take_until_first_healthy_module(sorted_modules_healthiness: list[Tuple[int, bool]]) -> list[int]:
        module_ids = []
        for module_id, is_healthy in sorted_modules_healthiness:
            module_ids.append(module_id)
            if is_healthy:
                break
        return module_ids
