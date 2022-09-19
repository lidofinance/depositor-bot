import logging
import time
from collections import defaultdict
from typing import List, Tuple

import timeout_decorator
from schema import Or, Schema
from web3 import Web3
from web3.exceptions import BlockNotFound, ContractLogicError, TransactionNotFound
from web3_multi_provider import NoActiveProviderError

import variables
from blockchain.buffered_eth import get_recommended_buffered_ether_to_deposit
from blockchain.contracts import contracts
from blockchain.fetch_latest_block import fetch_latest_block
from blockchain.gas_strategy import GasFeeStrategy
from cryptography.verify_signature import compute_vs
from metrics import healthcheck_pulse
from metrics.metrics import (
    BUILD_INFO,
    ACCOUNT_BALANCE,
    BUFFERED_ETHER,
    REQUIRED_BUFFERED_ETHER,
    GAS_FEE,
    OPERATORS_FREE_KEYS,
    CURRENT_QUORUM_SIZE,
    DEPOSIT_FAILURE,
    SUCCESS_DEPOSIT,
)
from metrics.transport_message_metrics import message_metrics
from transport.msg_providers.kafka import KafkaMessageProvider
from transport.msg_providers.rabbit import RabbitProvider, MessageType
from transport.msg_schemas import (
    DepositMessageSchema,
    PingMessageSchema,
    get_deposit_messages_sign_filter,
    DepositMessage,
)
from transport.msg_storage import MessageStorage


logger = logging.getLogger(__name__)


class DepositorBot:
    NOT_ENOUGH_BALANCE_ON_ACCOUNT = 'Account balance is too low.'
    GAS_FEE_HIGHER_THAN_RECOMMENDED = 'Gas fee is higher than recommended fee.'
    DEPOSIT_SECURITY_ISSUE = 'Deposit security module prohibits the deposit.'
    LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER = 'Lido contract has not enough buffered ether.'
    LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS = 'Lido contract has no free keys.'
    QUORUM_IS_NOT_READY = 'Quorum is not ready.'

    current_block = None
    deposit_root: str = None
    keys_op_index: int = None
    last_fb_deposit_failed = False

    def __init__(self, w3: Web3):
        logger.info({'msg': 'Initialize DepositorBot.'})
        self.w3 = w3

        self.gas_fee_strategy = GasFeeStrategy(w3, blocks_count_cache=150, max_gas_fee=variables.MAX_GAS_FEE)

        self.min_signs_to_deposit = contracts.deposit_security_module.functions.getGuardianQuorum().call()
        logger.info({'msg': f'Call `getGuardianQuorum()`.', 'value': self.min_signs_to_deposit})

        self.guardians_list = contracts.deposit_security_module.functions.getGuardians().call()
        logger.info({'msg': f'Call `getGuardians()`.', 'value': self.guardians_list})

        self.deposit_prefix = contracts.deposit_security_module.functions.ATTEST_MESSAGE_PREFIX().call()
        logger.info({'msg': 'Call `ATTEST_MESSAGE_PREFIX()`.', 'value': str(self.deposit_prefix)})

        self.message_storage = MessageStorage(
            transports=[
                KafkaMessageProvider(
                    client=f'{variables.KAFKA_GROUP_PREFIX}deposit',
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                ),
                RabbitProvider(
                    client='depositor',
                    routing_keys=[MessageType.PING, MessageType.DEPOSIT],
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                ),
            ],
            filters=[
                message_metrics,
                get_deposit_messages_sign_filter(self.deposit_prefix),
            ],
        )

        BUILD_INFO.labels(
            'Depositor bot',
            variables.NETWORK,
            variables.MAX_GAS_FEE,
            variables.MAX_BUFFERED_ETHERS,
            variables.CONTRACT_GAS_LIMIT,
            variables.GAS_FEE_PERCENTILE_1,
            variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1,
            variables.GAS_PRIORITY_FEE_PERCENTILE,
            variables.MIN_PRIORITY_FEE,
            variables.MAX_PRIORITY_FEE,
            variables.KAFKA_TOPIC,
            variables.ACCOUNT.address if variables.ACCOUNT else '0x0',
            variables.CREATE_TRANSACTIONS,
        )

    # ------------ CYCLE STAFF -------------------
    def run_as_daemon(self):
        """Super-Mega infinity cycle!"""
        while True:
            self._waiting_for_new_block_and_run_cycle()

    @timeout_decorator.timeout(variables.MAX_CYCLE_LIFETIME_IN_SECONDS)
    def _waiting_for_new_block_and_run_cycle(self):
        try:
            self.run_cycle()
        except BlockNotFound as error:
            logger.warning({'msg': 'Fetch block exception.', 'error': str(error)})
            # Waiting for new block
            time.sleep(15)
        except timeout_decorator.TimeoutError as exception:
            # Bot is stuck. Drop bot and restart using Docker service
            logger.error({'msg': 'Depositor bot do not respond.', 'error': str(exception)})
            raise timeout_decorator.TimeoutError('Depositor bot stuck. Restarting using docker service.') from exception
        except NoActiveProviderError as exception:
            logger.error({'msg': 'No active node available.', 'error': str(exception)})
            raise NoActiveProviderError from exception
        except ConnectionError as error:
            logger.error({'msg': error.args, 'error': str(error)})
            raise ConnectionError from error
        except ValueError as error:
            logger.error({'msg': error.args, 'error': str(error)})
            time.sleep(15)
        except Exception as error:
            logger.warning({'msg': 'Unexpected exception.', 'error': str(error)})
            time.sleep(15)
        else:
            time.sleep(15)

    def run_cycle(self):
        logger.info({'msg': 'New deposit cycle.'})
        self._update_state()

        deposit_issues = self.get_deposit_issues()

        if not deposit_issues:
            logger.info({'msg': f'No issues found.', 'value': deposit_issues})
            return self.do_deposit()

        logger.info({'msg': f'Issues found.', 'value': deposit_issues})

        long_issues = [
            self.NOT_ENOUGH_BALANCE_ON_ACCOUNT,
            self.DEPOSIT_SECURITY_ISSUE,
            self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER,
            self.LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS,
        ]

        for long_issue in long_issues:
            if long_issue in deposit_issues:
                logger.info({'msg': f'Long issue found. Sleep for 1 minute.', 'value': long_issue})
                time.sleep(60)
                break

    def _update_state(self):
        healthcheck_pulse.pulse()

        self.current_block = fetch_latest_block(self.w3, self.current_block.number if self.current_block else 0)

        self.deposit_root = '0x' + contracts.deposit_contract.functions.get_deposit_root().call(block_identifier=self.current_block.hash.hex()).hex()
        logger.info({'msg': f'Call `get_deposit_root()`.', 'value': str(self.deposit_root)})

        self.keys_op_index = contracts.node_operator_registry.functions.getKeysOpIndex().call(block_identifier=self.current_block.hash.hex())
        logger.info({'msg': f'Call `getKeysOpIndex()`.', 'value': self.keys_op_index})

    def get_deposit_issues(self) -> List[str]:
        deposit_issues = []

        if self._account_balance_issue():
            deposit_issues.append(self.NOT_ENOUGH_BALANCE_ON_ACCOUNT)

        if self._buffered_ether_issue():
            deposit_issues.append(self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)

        if self._high_gas_fee_issue():
            deposit_issues.append(self.GAS_FEE_HIGHER_THAN_RECOMMENDED)

        if self._prohibit_to_deposit_issue():
            deposit_issues.append(self.DEPOSIT_SECURITY_ISSUE)

        if self._available_keys_issue():
            deposit_issues.append(self.LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS)

        if self._quorum_issue():
            deposit_issues.append(self.QUORUM_IS_NOT_READY)

        return deposit_issues

    def _account_balance_issue(self) -> bool:
        if variables.ACCOUNT:
            balance = self.w3.eth.get_balance(variables.ACCOUNT.address, block_identifier={"blockHash": self.current_block.hash.hex()})
            ACCOUNT_BALANCE.set(balance)
            logger.info({'msg': 'Check account balance.', 'value': balance})
            if balance < self.w3.toWei(0.05, 'ether'):
                logger.warning({'msg': self.NOT_ENOUGH_BALANCE_ON_ACCOUNT, 'value': balance})
                return True
        else:
            logger.info({'msg': 'Check account balance. No account provided.'})
            ACCOUNT_BALANCE.set(0)

    def _buffered_ether_issue(self) -> bool:
        pending_gas_fee = self.w3.eth.get_block('pending').baseFeePerGas
        logger.info({'msg': 'Get pending `baseFeePerGas`.', 'value': pending_gas_fee})

        buffered_ether = contracts.lido.functions.getBufferedEther().call(block_identifier=self.current_block.hash.hex())
        logger.info({'msg': 'Call `getBufferedEther()`.', 'value': buffered_ether})
        BUFFERED_ETHER.set(buffered_ether)

        recommended_buffered_ether = get_recommended_buffered_ether_to_deposit(pending_gas_fee)
        logger.info({'msg': 'Recommended min buffered ether to deposit.', 'value': recommended_buffered_ether})
        REQUIRED_BUFFERED_ETHER.set(recommended_buffered_ether)

        if buffered_ether < recommended_buffered_ether:
            logger.warning({'msg': self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER, 'value': buffered_ether})
            return True

    def _high_gas_fee_issue(self) -> bool:
        current_gas_fee = self.w3.eth.get_block('pending').baseFeePerGas
        buffered_ether = contracts.lido.functions.getBufferedEther().call(block_identifier=self.current_block.hash.hex())

        is_high_buffer = buffered_ether >= variables.MAX_BUFFERED_ETHERS
        logger.info({'msg': 'Check max ether in buffer.', 'value': is_high_buffer})

        recommended_gas_fee = self.gas_fee_strategy.get_recommended_gas_fee((
            (variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1, variables.GAS_FEE_PERCENTILE_1),
        ), force=is_high_buffer)

        GAS_FEE.labels('max_fee').set(variables.MAX_GAS_FEE)
        GAS_FEE.labels('current_fee').set(current_gas_fee)
        GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)

        if current_gas_fee > recommended_gas_fee:
            logger.info({
                'msg': self.GAS_FEE_HIGHER_THAN_RECOMMENDED,
                'values': {
                    'max_fee': variables.MAX_GAS_FEE,
                    'current_fee': current_gas_fee,
                    'recommended_fee': recommended_gas_fee,
                    'buffered_ether': buffered_ether,
                }
            })
            return True

    def _prohibit_to_deposit_issue(self) -> bool:
        can_deposit = contracts.deposit_security_module.functions.canDeposit().call(block_identifier=self.current_block.hash.hex())
        logger.info({'msg': 'Call `canDeposit()`.', 'value': can_deposit})

        if not can_deposit:
            logger.warning({'msg': self.DEPOSIT_SECURITY_ISSUE, 'value': can_deposit})
            return True

    def _available_keys_issue(self) -> bool:
        available_keys = contracts.node_operator_registry.functions.assignNextSigningKeys(1).call(
            {'from': contracts.lido.address},
            block_identifier=self.current_block.hash.hex(),
        )[0]

        OPERATORS_FREE_KEYS.set(1 if available_keys else 0)
        logger.info({'msg': 'Call `assignNextSigningKeys()`.', 'value': bool(available_keys)})

        if not available_keys:
            logger.warning({'msg': self.LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS})
            return True

    def _quorum_issue(self) -> bool:

        def _actualize_message(message: DepositMessage):
            if message['type'] != 'deposit':
                return False

            # Maybe council daemon already reports next block
            if message['blockNumber'] <= self.current_block.number:
                if message['keysOpIndex'] != self.keys_op_index:
                    return False

                if message['depositRoot'] != self.deposit_root:
                    return False

                if message['blockNumber'] + 200 < self.current_block.number:
                    return False

            if message['guardianAddress'] not in self.guardians_list:
                return False

            return True

        self.message_storage.update_messages()
        self.message_storage.get_messages(_actualize_message)

        quorum_messages = self._form_a_quorum()

        CURRENT_QUORUM_SIZE.set(len(quorum_messages))
        if len(quorum_messages) < self.min_signs_to_deposit:
            logger.warning({'msg': self.QUORUM_IS_NOT_READY})
            return True

    def _form_a_quorum(self) -> List[DepositMessage]:
        dict_for_sort = defaultdict(lambda: defaultdict(list))

        for message in self.message_storage.messages:
            dict_for_sort[message['blockNumber']][message['blockHash']].append(message)

        max_quorum = 0
        quorum_block_number = 0
        quorum_block_hash = ''

        for block_num, blocks_by_number in dict_for_sort.items():
            for block_hash, block_messages in blocks_by_number.items():

                if max_quorum < len(block_messages) and block_num > quorum_block_number:
                    max_quorum = len(block_messages)
                    quorum_block_number = block_num
                    quorum_block_hash = block_hash

        quorum_messages = self._remove_address_duplicates(dict_for_sort[quorum_block_number][quorum_block_hash])

        if max_quorum >= self.min_signs_to_deposit:
            logger.info({'msg': f'Quorum ready.', 'value': quorum_messages})
        else:
            logger.warning({'msg': 'Not enough signs for quorum.', 'value': max_quorum})

        return quorum_messages

    @staticmethod
    def _remove_address_duplicates(messages: List[DepositMessage]) -> List[DepositMessage]:
        guardian_address = []

        def _filter(msg: DepositMessage) -> bool:
            if msg['guardianAddress'] not in guardian_address:
                guardian_address.append(msg['guardianAddress'])
                return True

        return list(filter(_filter, messages))

    def do_deposit(self):
        quorum = self._form_a_quorum()

        priority = self.gas_fee_strategy.get_priority_fee(
            variables.GAS_PRIORITY_FEE_PERCENTILE,
            variables.MIN_PRIORITY_FEE,
            variables.MAX_PRIORITY_FEE,
        )

        signs = self._prepare_signs(quorum)

        logger.info({'msg': 'Sending deposit transaction.', 'values': {
            'deposit_root': str(self.deposit_root),
            'keys_op_index': self.keys_op_index,
            'block_number': quorum[0]['blockNumber'],
            'block_hash': quorum[0]['blockHash'],
            'signs': signs,
            'gas_limit': variables.CONTRACT_GAS_LIMIT,
            'priority_fee': priority,
        }})

        if not variables.ACCOUNT:
            logger.info({'msg': 'Account was not provided.'})
            return

        if not variables.CREATE_TRANSACTIONS:
            logger.info({'msg': 'Run in dry mode.'})
            return

        deposit_function = contracts.deposit_security_module.functions.depositBufferedEther(
            self.deposit_root,
            self.keys_op_index,
            quorum[0]['blockNumber'],
            quorum[0]['blockHash'],
            signs,
        )

        try:
            deposit_function.call()
        except ContractLogicError as error:
            logger.error({'msg': 'Local transaction reverted.', 'error': str(error)})
            return

        logger.info({'msg': 'Transaction call completed successfully.'})

        transaction = deposit_function.build_transaction({
            'from': variables.ACCOUNT.address,
            'gas': variables.CONTRACT_GAS_LIMIT,
            'maxFeePerGas': self.current_block.baseFeePerGas * 2 + priority,
            'maxPriorityFeePerGas': priority,
            "nonce": self.w3.eth.get_transaction_count(variables.ACCOUNT.address),
        })

        signed = self.w3.eth.account.sign_transaction(transaction, variables.ACCOUNT.privateKey)

        if self.last_fb_deposit_failed:
            self._do_classic_deposit(signed)
        else:
            self._do_flashbots_deposit(signed)

        logger.info({'msg': f'Deposit method end. Sleep for 1 minute.'})
        time.sleep(60)

    def _do_classic_deposit(self, signed_transaction):
        self.last_fb_deposit_failed = False

        logger.info({'msg': 'Try to deposit. Classic mode.'})

        try:
            result = self.w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
        except Exception as error:
            logger.error({'msg': 'Transaction reverted.', 'value': str(error)})
            DEPOSIT_FAILURE.inc()
        else:
            logger.info({'msg': 'Transaction mined.', 'value': result.hex()})
            SUCCESS_DEPOSIT.inc()

    def _do_flashbots_deposit(self, signed_transaction):
        logger.info({'msg': 'Try to deposit. Flashbots mode.'})

        for i in range(7):
            # Try to get in next 7 blocks
            result = self.w3.flashbots.send_bundle(
                [{"signed_transaction": signed_transaction.rawTransaction}],
                self.current_block.number + 1 + i
            )

        try:
            rec = result.receipts()
        except TransactionNotFound as error:
            self.last_fb_deposit_failed = True
            logger.error({'msg': f'Deposit failed.', 'error': str(error)})
            DEPOSIT_FAILURE.inc()
        else:
            logger.info({'msg': 'Transaction mined.', 'value': rec[-1]['transactionHash'].hex()})
            SUCCESS_DEPOSIT.inc()

    @staticmethod
    def _prepare_signs(messages: List[DepositMessage]) -> List[Tuple[str, str]]:
        sorted_messages = sorted(messages, key=lambda msg: int(msg['guardianAddress'], 16))

        return [
            (msg['signature']['r'], compute_vs(msg['signature']['v'], msg['signature']['s']))
            for msg in sorted_messages
        ]
