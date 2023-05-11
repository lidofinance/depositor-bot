import logging
import traceback
import time
from collections import defaultdict
from typing import List, Tuple, Optional

import timeout_decorator
from schema import Or, Schema
from web3 import Web3
from web3.exceptions import BlockNotFound, ContractLogicError, TransactionNotFound
from web3_multi_provider import NoActiveProviderError

import variables
from blockchain.buffered_eth import get_recommended_buffered_ether_to_deposit
from blockchain.constants import FLASHBOTS_RPC
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
    CAN_DEPOSIT_KEYS,
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
from variables_types import TransportType


logger = logging.getLogger(__name__)


MODULE_ID = 1


class DepositorBot:
    NOT_ENOUGH_BALANCE_ON_ACCOUNT = 'Account balance is too low.'
    GAS_FEE_HIGHER_THAN_RECOMMENDED = 'Gas fee is higher than recommended fee.'
    DEPOSIT_SECURITY_ISSUE = 'Deposit security module prohibits the deposit.'
    LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER = 'Lido contract has not enough buffered ether.'
    DEPOSITOR_CAN_DEPOSIT_KEYS = 'Depositor can not deposit keys. ' \
                                 'No keys, paused staking module or not enough reserved ether.'
    QUORUM_IS_NOT_READY = 'Quorum is not ready.'

    current_block = None
    deposit_root: str = None
    nonce: int = None
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
            logger.error({'msg': 'No transports found', 'value': variables.MESSAGE_TRANSPORTS})
            raise ValueError(f'No transports found. Provided value: {variables.MESSAGE_TRANSPORTS}')

        self.message_storage = MessageStorage(
            transports,
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
            logger.warning({'msg': 'Unexpected exception.', 'error': str(error), 'details': traceback.format_exc()})
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
            self.DEPOSITOR_CAN_DEPOSIT_KEYS,
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

        # TODO replace nonce with getStakingModuleNonce
        self.nonce = self._get_nonce()
        logger.info({'msg': f'Call `getKeysOpIndex()`.', 'value': self.nonce})

    def _get_nonce(self) -> int:
        return contracts.node_operator_registry.functions.getKeysOpIndex().call(block_identifier=self.current_block.hash.hex())

    def get_deposit_issues(self) -> List[str]:
        # Filter non-valid messages. Actualized messages will be used in various checks.
        self.actualize_messages()

        deposit_issues = []

        if self._account_balance_issue():
            deposit_issues.append(self.NOT_ENOUGH_BALANCE_ON_ACCOUNT)

        if self._buffered_ether_issue():
            deposit_issues.append(self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)

        if self._high_gas_fee_issue():
            deposit_issues.append(self.GAS_FEE_HIGHER_THAN_RECOMMENDED)

        if self._quorum_issue():
            deposit_issues.append(self.QUORUM_IS_NOT_READY)

        # if staking_module_id is None deposit_issues would contain QUORUM_IS_NOT_READY because there is no messages
        staking_module_id = self._get_latest_staking_module_id_in_messages()
        if staking_module_id:
            if self._prohibit_to_deposit_issue(staking_module_id):
                deposit_issues.append(self.DEPOSIT_SECURITY_ISSUE)

            if self._cen_deposit_keys_issue(staking_module_id):
                deposit_issues.append(self.DEPOSITOR_CAN_DEPOSIT_KEYS)

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

        buffered_ether = contracts.lido.functions.getDepositableEther().call(
            block_identifier=self.current_block.hash.hex(),
        )
        logger.info({'msg': 'Call `getDepositableEther()`.', 'value': buffered_ether})
        BUFFERED_ETHER.set(buffered_ether)

        recommended_buffered_ether = get_recommended_buffered_ether_to_deposit(pending_gas_fee)
        logger.info({'msg': 'Recommended min buffered ether to deposit.', 'value': recommended_buffered_ether})
        REQUIRED_BUFFERED_ETHER.set(recommended_buffered_ether)

        if buffered_ether < recommended_buffered_ether:
            logger.warning({'msg': self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER, 'value': buffered_ether})
            return True

    def _high_gas_fee_issue(self) -> bool:
        current_gas_fee = self.w3.eth.get_block('pending').baseFeePerGas
        buffered_ether = contracts.lido.functions.getDepositableEther().call(
            block_identifier=self.current_block.hash.hex(),
        )

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

    def _prohibit_to_deposit_issue(self, staking_module_id: int) -> bool:
        can_deposit = contracts.deposit_security_module.functions.canDeposit(staking_module_id).call(
            block_identifier=self.current_block.hash.hex(),
        )
        logger.info({'msg': 'Call canDeposit().', 'value': can_deposit})

        if not can_deposit:
            logger.warning({'msg': self.DEPOSIT_SECURITY_ISSUE, 'value': can_deposit})
            return True

    def _cen_deposit_keys_issue(self, staking_module_id: int) -> bool:
        depositable_ether = contracts.lido.functions.getDepositableEther().call(
            block_identifier=self.current_block.hash.hex(),
        )
        possible_deposits = contracts.staking_router.functions.getStakingModuleMaxDepositsCount(
            staking_module_id,
            depositable_ether,
        ).call(
            block_identifier=self.current_block.hash.hex(),
        )
        logger.info({
            'msg': f'Call getStakingModuleMaxDepositsCount({staking_module_id}, {depositable_ether}).',
            'value': possible_deposits,
        })

        CAN_DEPOSIT_KEYS.set(1 if possible_deposits else 0)

        if not possible_deposits:
            logger.warning({'msg': self.DEPOSITOR_CAN_DEPOSIT_KEYS})
            return True

    def _quorum_issue(self) -> bool:
        quorum_messages = self._form_a_quorum()

        CURRENT_QUORUM_SIZE.set(len(quorum_messages))

        if len(quorum_messages) < self.min_signs_to_deposit:
            logger.warning({'msg': self.QUORUM_IS_NOT_READY})
            return True

    def actualize_messages(self):
        def _actualize_messages(message: DepositMessage):
            if message['type'] != 'deposit':
                logger.info({'msg': f'_actualize_message message.type issue', 'value': message['type']})
                return False

            # Maybe council daemon already reports next block
            if message['blockNumber'] <= self.current_block.number:
                if message['nonce'] != self.nonce:
                    logger.info({'msg': f'_actualize_message message.nonce issue', 'value': message['nonce']})
                    return False

                if message['depositRoot'] != self.deposit_root:
                    logger.info({'msg': f'_actualize_message message.depositRoot issue', 'value': message['depositRoot']})
                    return False

                if message['blockNumber'] + 200 < self.current_block.number:
                    logger.info({'msg': f'_actualize_message message.blockNumber issue', 'value': message['blockNumber']})
                    return False

            if message['guardianAddress'] not in self.guardians_list:
                logger.info({'msg': f'_actualize_message message.guardianAddress issue', 'value': message['guardianAddress']})
                return False

            return True

        self.message_storage.update_messages()
        self.message_storage.get_messages(_actualize_messages)

    def _get_latest_staking_module_id_in_messages(self) -> Optional[int]:
        messages = self._form_a_quorum()
        if messages:
            return messages[0]['stakingModuleId']

    def _form_a_quorum(self) -> List[DepositMessage]:
        dict_for_sort = defaultdict(lambda: defaultdict(list))

        for message in self.message_storage.messages:
            logger.debug({'msg': f'dict_for_sort message.', 'value': message})
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

    @staticmethod
    def _check_transaction(transaction) -> bool:
        try:
            transaction.call()
        except ContractLogicError as error:
            logger.error({'msg': 'Local transaction reverted.', 'error': str(error)})
            return False

        return True

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
            'nonce': self.nonce,
            'block_number': quorum[0]['blockNumber'],
            'block_hash': quorum[0]['blockHash'],
            'signs': signs,
            'gas_limit': variables.CONTRACT_GAS_LIMIT,
            'priority_fee': priority,
        }})

        deposit_function = contracts.deposit_security_module.functions.depositBufferedEther(
            quorum[0]['blockNumber'],
            quorum[0]['blockHash'],
            self.deposit_root,
            quorum[0]['stakingModuleId'],
            self.nonce,
            b'',
            signs,
        )

        if not self._check_transaction(deposit_function):
            return

        logger.info({'msg': 'Deposit local call succeed.'})

        if not variables.ACCOUNT:
            logger.info({'msg': 'Account was not provided.'})
            return

        if not variables.CREATE_TRANSACTIONS:
            logger.info({'msg': 'Run in dry mode.'})
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

        if (
            variables.FLASHBOT_SIGNATURE is not None
            and variables.WEB3_CHAIN_ID in FLASHBOTS_RPC
            and not self.last_fb_deposit_failed
        ):
            self._do_flashbots_deposit(signed)
        else:
            self._do_classic_deposit(signed)

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
