import logging
import time
from collections import defaultdict
from typing import List, Tuple

from brownie import web3, Wei, chain
from hexbytes import HexBytes
from web3 import HTTPProvider, WebsocketProvider
from web3.exceptions import BlockNotFound

from scripts.depositor_utils.kafka import DepositBotMsgRecipient
from scripts.utils.constants import FLASHBOTS_RPC, INFURA_URL
from scripts.utils.interfaces import (
    DepositSecurityModuleInterface,
    DepositContractInterface,
    NodeOperatorsRegistryInterface,
    LidoInterface,
)
from scripts.utils.metrics import (
    ACCOUNT_BALANCE,
    GAS_FEE,
    BUFFERED_ETHER,
    OPERATORS_FREE_KEYS,
    DEPOSIT_FAILURE,
    SUCCESS_DEPOSIT,
    CURRENT_QUORUM_SIZE,
    CREATING_TRANSACTIONS, BUILD_INFO,
)
from scripts.utils import variables
from scripts.utils.gas_strategy import GasFeeStrategy


logger = logging.getLogger(__name__)


class DepositorBot:
    NOT_ENOUGH_BALANCE_ON_ACCOUNT = 'Account balance is too low.'
    GAS_FEE_HIGHER_THAN_RECOMMENDED = 'Gas fee is higher than recommended fee.'
    DEPOSIT_SECURITY_ISSUE = 'Deposit security module prohibits the deposit.'
    LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER = 'Lido contract has not enough buffered ether.'
    LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS = 'Lido contract has no free keys.'
    QUORUM_IS_NOT_READY = 'Quorum is not ready'

    _current_block = None

    def __init__(self):
        logger.info({'msg': 'Initialize DepositorBot.'})
        self.gas_fee_strategy = GasFeeStrategy(web3, blocks_count_cache=150, max_gas_fee=variables.MAX_GAS_FEE)

        self.kafka = DepositBotMsgRecipient(client=f'{variables.KAFKA_GROUP_PREFIX}deposit')

        # Some rarely change things
        self._load_constants()
        logger.info({'msg': 'Depositor bot initialize done'})

        BUILD_INFO.labels(
            'Depositor bot',
            variables.NETWORK,
            variables.MAX_GAS_FEE,
            variables.CONTRACT_GAS_LIMIT,
            variables.GAS_FEE_PERCENTILE_1,
            variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1,
            variables.GAS_FEE_PERCENTILE_2,
            variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_2,
            variables.GAS_PRIORITY_FEE_PERCENTILE,
            variables.MIN_PRIORITY_FEE,
            variables.MAX_PRIORITY_FEE,
            variables.KAFKA_TOPIC,
            variables.ACCOUNT.address if variables.ACCOUNT else '0x0',
            variables.CREATE_TRANSACTIONS,
        )

    def _load_constants(self):
        self.min_signs_to_deposit = DepositSecurityModuleInterface.getGuardianQuorum()
        logger.info({'msg': f'Call `getGuardianQuorum()`.', 'value': self.min_signs_to_deposit})

        self.deposit_prefix = DepositSecurityModuleInterface.ATTEST_MESSAGE_PREFIX()
        logger.info({'msg': 'Call `ATTEST_MESSAGE_PREFIX()`.', 'value': str(self.deposit_prefix)})

        if variables.CREATE_TRANSACTIONS:
            CREATING_TRANSACTIONS.labels('deposit').set(1)
        else:
            CREATING_TRANSACTIONS.labels('deposit').set(0)

    # ------------ CYCLE STAFF -------------------
    def run_as_daemon(self):
        """Super-Mega infinity cycle!"""
        while True:
            try:
                for _ in chain.new_blocks():
                    self.run_cycle()
            except (BlockNotFound, ValueError) as error:
                logger.warning({'msg': 'Fetch block exception.', 'error': str(error)})
                # Waiting for new block
                time.sleep(13)
            except Exception as error:
                logger.warning({'msg': 'Unexpected exception.', 'error': str(error)})
                time.sleep(13)

    def run_cycle(self):
        """
        Fetch latest signs from
        """
        logger.info({'msg': 'New deposit cycle.'})
        self._update_state()

        # Pause message instantly if we receive pause message
        deposit_issues = self.get_deposit_issues()

        if not deposit_issues:
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
        self._current_block = web3.eth.get_block('latest')
        logger.info({'msg': f'Fetch `latest` block.', 'value': self._current_block.number})

        self.deposit_root = DepositContractInterface.get_deposit_root(block_identifier=self._current_block.hash.hex())
        logger.info({'msg': f'Call `get_deposit_root()`.', 'value': str(self.deposit_root)})

        self.keys_op_index = NodeOperatorsRegistryInterface.getKeysOpIndex(block_identifier=self._current_block.hash.hex())
        logger.info({'msg': f'Call `getKeysOpIndex()`.', 'value': self.keys_op_index})

        self.kafka.update_messages()

    # ------------- FIND ISSUES -------------------
    def get_deposit_issues(self) -> List[str]:
        """Do a lot of checks and send all things why deposit could not be done"""
        deposit_issues = []

        # ------- Other checks -------
        if variables.ACCOUNT:
            balance = web3.eth.get_balance(variables.ACCOUNT.address)
            ACCOUNT_BALANCE.set(balance)
            if balance < Wei('0.05 ether'):
                logger.warning({'msg': self.NOT_ENOUGH_BALANCE_ON_ACCOUNT, 'value': balance})
                deposit_issues.append(self.NOT_ENOUGH_BALANCE_ON_ACCOUNT)

            else:
                logger.info({'msg': 'Check account balance.', 'value': balance})

        else:
            ACCOUNT_BALANCE.set(0)
            logger.info({'msg': 'Check account balance. No account provided.'})

        # Gas price check
        recommended_gas_fee = self.gas_fee_strategy.get_recommended_gas_fee((
            (variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1, variables.GAS_FEE_PERCENTILE_1),
            (variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_2, variables.GAS_FEE_PERCENTILE_2),
        ))

        current_gas_fee = web3.eth.get_block('pending').baseFeePerGas

        GAS_FEE.labels('max_fee').set(variables.MAX_GAS_FEE)
        GAS_FEE.labels('current_fee').set(current_gas_fee)
        GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)

        logger.info({'msg': 'Fetch gas fees.', 'values': {
            'max_fee': variables.MAX_GAS_FEE,
            'current_fee': current_gas_fee,
            'recommended_fee': recommended_gas_fee,
        }})

        if current_gas_fee > recommended_gas_fee:
            logger.warning({
                'msg': self.GAS_FEE_HIGHER_THAN_RECOMMENDED,
                'values': {
                    'max_fee': variables.MAX_GAS_FEE,
                    'current_fee': current_gas_fee,
                    'recommended_fee': recommended_gas_fee,
                }
            })
            deposit_issues.append(self.GAS_FEE_HIGHER_THAN_RECOMMENDED)

        can_deposit = DepositSecurityModuleInterface.canDeposit(block_identifier=self._current_block.hash.hex())
        logger.info({'msg': 'Call `canDeposit()`.', 'value': can_deposit})
        if not can_deposit:
            logger.warning({'msg': self.DEPOSIT_SECURITY_ISSUE, 'value': can_deposit})
            deposit_issues.append(self.DEPOSIT_SECURITY_ISSUE)

        # Lido contract buffered ether check
        buffered_ether = LidoInterface.getBufferedEther(block_identifier=self._current_block.hash.hex())
        logger.info({'msg': 'Call `getBufferedEther()`.', 'value': buffered_ether})
        BUFFERED_ETHER.set(buffered_ether)

        recommended_buffered_ether = self.gas_fee_strategy.get_recommended_buffered_ether_to_deposit(current_gas_fee)
        logger.info({'msg': 'Recommended min buffered ether to deposit.', 'value': recommended_buffered_ether})
        if buffered_ether < recommended_buffered_ether:
            logger.warning({'msg': self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER, 'value': buffered_ether})
            deposit_issues.append(self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)

        # Check that contract has unused operators keys
        avail_keys = NodeOperatorsRegistryInterface.assignNextSigningKeys.call(1, {'from': LidoInterface.address})[0]
        has_keys = bool(avail_keys)
        OPERATORS_FREE_KEYS.set(1 if has_keys else 0)
        logger.info({'msg': 'Call `getNodeOperator()` and `getNodeOperatorsCount()`. Value is free keys', 'value': has_keys})

        if not has_keys:
            logger.warning({'msg': self.LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS, 'value': has_keys})
            deposit_issues.append(self.LIDO_CONTRACT_HAS_NO_FREE_SUBMITTED_KEYS)

        # Check all signs
        # self._get_deposit_params()
        signs = self._get_deposit_params(self.deposit_root, self.keys_op_index)
        if signs is None:
            logger.warning({'msg': self.QUORUM_IS_NOT_READY})
            deposit_issues.append(self.QUORUM_IS_NOT_READY)

        return deposit_issues

    # ------------ DO DEPOSIT ------------------
    def do_deposit(self):
        """Sign and Make deposit"""
        logger.info({'msg': 'No issues found. Try to deposit.'})
        deposit_params = self._get_deposit_params(self.deposit_root, self.keys_op_index)

        if not deposit_params:
            logger.info({'msg': 'Failed to deposit. Too small quorum to deposit.'})
            return

        priority = self._get_deposit_priority_fee(variables.GAS_PRIORITY_FEE_PERCENTILE)

        logger.info({'msg': 'Sending deposit transaction.', 'values': {
            'deposit_root': str(self.deposit_root),
            'keys_op_index': str(self.keys_op_index),
            'block_number': deposit_params['block_num'],
            'block_hash': deposit_params['block_hash'].hex(),
            'signs': deposit_params['signs'],
            'gas_limit': variables.CONTRACT_GAS_LIMIT,
            'priority_fee': priority,
        }})

        if not variables.ACCOUNT:
            logger.info({'msg': 'Account was not provided.'})
            return

        if not variables.CREATE_TRANSACTIONS:
            logger.info({'msg': 'Run in dry mode.'})
            return

        logger.info({'msg': 'Creating tx in blockchain.'})

        provider = web3.provider
        web3.disconnect()
        web3.provider = HTTPProvider(FLASHBOTS_RPC[variables.WEB3_CHAIN_ID])

        try:
            result = DepositSecurityModuleInterface.depositBufferedEther(
                self.deposit_root,
                self.keys_op_index,
                deposit_params['block_num'],
                deposit_params['block_hash'],
                deposit_params['signs'],
                {
                    'gas_limit': variables.CONTRACT_GAS_LIMIT,
                    'priority_fee': priority,
                },
            )
        except Exception as error:
            logger.error({'msg': f'Deposit failed.', 'error': str(error)})
            DEPOSIT_FAILURE.inc()

        else:
            logger.info({'msg': f'Deposited successfully.', 'value': str(result.logs)})
            SUCCESS_DEPOSIT.inc()

        web3.disconnect()
        web3.provider = provider

        logger.info({'msg': f'Deposit method end. Sleep for 1 minute.'})
        time.sleep(60)

    def _get_deposit_params(self, deposit_root, keys_op_index):
        """
        Get all signs from kafka.
        Make sure they are from one block_num.
        Check sign count is enough for deposit.
        Generate own sign.
        Return signs.
        """

        # Fetch latest messages from kafka
        self.kafka.update_messages()

        sign_messages = self.kafka.get_deposit_messages(
            block_number=self._current_block.number,
            deposit_root=deposit_root,
            keys_op_index=keys_op_index,
        )

        dict_for_sort = defaultdict(lambda: defaultdict(list))

        for message in sign_messages:
            dict_for_sort[message['blockNumber']][message['blockHash']].append(message)

        max_quorum = 0

        for block_num, blocks_by_number in dict_for_sort.items():
            for block_hash, block_messages in blocks_by_number.items():

                max_quorum = max(len(block_messages), max_quorum)
                if len(block_messages) >= self.min_signs_to_deposit:
                    # Take the oldest messages to prevent reorganizations
                    logger.info({'msg': f'Quorum ready.', 'value': block_messages})
                    CURRENT_QUORUM_SIZE.set(max_quorum)

                    return {
                        'signs': self._from_messages_to_signs(block_messages),
                        'block_num': block_num,
                        'block_hash': HexBytes(block_hash),
                    }
                else:
                    logger.info({
                        'msg': f'Too small quorum',
                        'value': block_messages,
                        'block_number': block_num,
                        'block_hash': block_hash,
                    })

        CURRENT_QUORUM_SIZE.set(max_quorum)
        logger.warning({'msg': 'Not enough signs for quorum.', 'value': max_quorum})

    @staticmethod
    def _from_messages_to_signs(messages) -> List[Tuple[int, int]]:
        signs_dict = [
            {
                'address': msg['guardianAddress'],
                'sign': (msg['signature']['r'], msg['signature']['_vs']),
            }
            for msg in messages
        ]

        sorted_signs = sorted(signs_dict, key=lambda msg: int(msg['address'], 16))
        sorted_signs = [sign['sign'] for sign in sorted_signs]

        return sorted_signs

    @staticmethod
    def _get_deposit_priority_fee(percentile):
        return min(
            max(
                web3.eth.fee_history(1, 'latest', reward_percentiles=[percentile])['reward'][0][0],
                variables.MIN_PRIORITY_FEE,
            ),
            variables.MAX_PRIORITY_FEE,
        )
