import logging
import time
from collections import defaultdict
from typing import List, Tuple

from brownie import web3, Wei, chain
from hexbytes import HexBytes
from web3.exceptions import BlockNotFound

from scripts.depositor_utils.kafka import DepositBotMsgRecipient
from scripts.utils.interfaces import DepositSecurityModuleInterface, DepositContractInterface, \
    NodeOperatorsRegistryInterface, LidoInterface
from scripts.utils.metrics import ACCOUNT_BALANCE, GAS_FEE, BUFFERED_ETHER, OPERATORS_FREE_KEYS, DEPOSIT_FAILURE, \
    SUCCESS_DEPOSIT, CURRENT_QUORUM_SIZE, CREATING_TRANSACTIONS
from scripts.utils.variables import (
    MAX_GAS_FEE,
    CONTRACT_GAS_LIMIT,
    MIN_BUFFERED_ETHER,
    GAS_PRIORITY_FEE_PERCENTILE,
    GAS_FEE_PERCENTILE,
    GAS_FEE_PERCENTILE_DAYS_HISTORY, ACCOUNT, CREATE_TRANSACTIONS,
)
from scripts.utils.gas_strategy import GasFeeStrategy


logger = logging.getLogger(__name__)


class DepositorBot:
    NOT_ENOUGH_BALANCE_ON_ACCOUNT = 'Account balance is too low.'
    GAS_FEE_HIGHER_THAN_RECOMMENDED = 'Gas fee is higher than recommended fee.'
    DEPOSIT_SECURITY_ISSUE = 'Deposit security module prohibits the deposit.'
    LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER = 'Lido contract has not enough buffered ether.'
    LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS = 'Lido contract has not enough submitted keys.'
    QUORUM_IS_NOT_READY = 'Quorum is not ready'

    _current_block = None

    def __init__(self):
        logger.info({'msg': 'Initialize DepositorBot.'})
        self.gas_fee_strategy = GasFeeStrategy(web3, max_gas_fee=MAX_GAS_FEE)
        self.kafka = DepositBotMsgRecipient(client='deposit')

        # Some rarely change things
        self._load_constants()
        logger.info({'msg': 'Depositor bot initialize done'})

    def _load_constants(self):
        self.min_signs_to_deposit = DepositSecurityModuleInterface.getGuardianQuorum()
        logger.info({'msg': f'Call `getGuardianQuorum()`.', 'value': self.min_signs_to_deposit})

        self.deposit_prefix = DepositSecurityModuleInterface.ATTEST_MESSAGE_PREFIX()
        logger.info({'msg': 'Call `ATTEST_MESSAGE_PREFIX()`.', 'value': str(self.deposit_prefix)})

        if CREATE_TRANSACTIONS:
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
            except BlockNotFound as error:
                logger.warning({'msg': 'Fetch block exception (BlockNotFound)', 'error': str(error)})
                # Waiting for new block
                time.sleep(10)

    def run_cycle(self):
        """
        Fetch latest signs from
        """
        logger.info({'msg': 'New deposit cycle.'})
        self._update_state()

        # Pause message instantly if we receive pause message
        deposit_issues = self.get_deposit_issues()

        if not deposit_issues:
            self.do_deposit()

        elif [self.GAS_FEE_HIGHER_THAN_RECOMMENDED] != deposit_issues:
            # Gas fee issues can be changed in any block. So don't sleep
            logger.info({'msg': f'Issues found. Sleep for 5 minutes.', 'value': deposit_issues})
            time.sleep(300)

    def _update_state(self):
        self._current_block = web3.eth.get_block('latest')
        logger.info({'msg': f'Fetch `latest` block.', 'value': self._current_block.number})

        self.deposit_root = DepositContractInterface.get_deposit_root()
        logger.info({'msg': f'Call `get_deposit_root()`.', 'value': str(self.deposit_root)})

        self.keys_op_index = NodeOperatorsRegistryInterface.getKeysOpIndex()
        logger.info({'msg': f'Call `getKeysOpIndex()`.', 'value': self.keys_op_index})

        self.kafka.update_messages()

    # ------------- FIND ISSUES -------------------
    def get_deposit_issues(self) -> List[str]:
        """Do a lot of checks and send all things why deposit could not be done"""
        deposit_issues = []

        # ------- Other checks -------
        if ACCOUNT:
            balance = web3.eth.get_balance(ACCOUNT.address)
            ACCOUNT_BALANCE.set(balance)
            if balance < Wei('0.01 ether'):
                logger.warning({'msg': 'Account balance is low.', 'value': balance})
                deposit_issues.append(self.NOT_ENOUGH_BALANCE_ON_ACCOUNT)

            else:
                logger.info({'msg': 'Check account balance.', 'value': balance})

        else:
            ACCOUNT_BALANCE.set(0)
            logger.info({'msg': 'Check account balance. No account provided.'})

        # Gas price check
        recommended_gas_fee = self.gas_fee_strategy.get_gas_fee_percentile(
            GAS_FEE_PERCENTILE_DAYS_HISTORY,
            GAS_FEE_PERCENTILE,
        )
        current_gas_fee = self._current_block.baseFeePerGas

        GAS_FEE.labels('max_fee').set(MAX_GAS_FEE)
        GAS_FEE.labels('current_fee').set(current_gas_fee)
        GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)

        logger.info({'msg': 'Fetch gas fees.', 'values': {
            'max_fee': MAX_GAS_FEE,
            'current_fee': current_gas_fee,
            'recommended_fee': recommended_gas_fee,
        }})

        if current_gas_fee > recommended_gas_fee:
            logger.warning({
                'msg': self.GAS_FEE_HIGHER_THAN_RECOMMENDED,
                'values': {
                    'max_fee': MAX_GAS_FEE,
                    'current_fee': current_gas_fee,
                    'recommended_fee': recommended_gas_fee,
                }
            })
            deposit_issues.append(self.GAS_FEE_HIGHER_THAN_RECOMMENDED)

        can_deposit = DepositSecurityModuleInterface.canDeposit()
        logger.info({'msg': 'Call `canDeposit()`.', 'value': can_deposit})
        if not can_deposit:
            logger.warning({'msg': 'Deposit security module prohibits deposits.', 'value': can_deposit})
            deposit_issues.append(self.DEPOSIT_SECURITY_ISSUE)

        # Lido contract buffered ether check
        buffered_ether = LidoInterface.getBufferedEther()
        logger.info({'msg': 'Call `getBufferedEther()`.', 'value': buffered_ether})
        BUFFERED_ETHER.set(buffered_ether)
        if buffered_ether < MIN_BUFFERED_ETHER:
            logger.warning({'msg': self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER, 'value': buffered_ether})
            deposit_issues.append(self.LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)

        # Check that contract has unused operators keys
        free_keys = self._get_operators_free_keys_count()
        OPERATORS_FREE_KEYS.set(free_keys)
        logger.info({'msg': 'Call `getNodeOperator()` and `getNodeOperatorsCount()`. Value is free keys', 'value': free_keys})

        if not free_keys:
            logger.warning({'msg': self.LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS, 'value': free_keys})
            deposit_issues.append(self.LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS)

        # Check all signs
        # self._get_deposit_params()
        signs = self._get_deposit_params(self.deposit_root, self.keys_op_index)
        if signs is None:
            logger.warning({'msg': self.QUORUM_IS_NOT_READY})
            deposit_issues.append(self.QUORUM_IS_NOT_READY)

        return deposit_issues

    def _get_operators_free_keys_count(self):
        operators_data = [
            {**NodeOperatorsRegistryInterface.getNodeOperator(i, True)}
            for i in range(NodeOperatorsRegistryInterface.getNodeOperatorsCount())
        ]

        free_keys = 0

        for operator in operators_data:
            free_keys += self._get_operator_free_keys_count(operator)

        OPERATORS_FREE_KEYS.set(free_keys)

        return free_keys

    @staticmethod
    def _get_operator_free_keys_count(operator: dict) -> int:
        """Check if operator has free keys"""
        free_space = operator['stakingLimit'] - operator['usedSigningKeys']
        keys_to_deposit = operator['totalSigningKeys'] - operator['usedSigningKeys']
        return min(free_space, keys_to_deposit)

    # ------------ DO DEPOSIT ------------------
    def do_deposit(self):
        """Sign and Make deposit"""
        logger.info({'msg': 'No issues found. Try to deposit.'})
        deposit_params = self._get_deposit_params(self.deposit_root, self.keys_op_index)

        if not deposit_params:
            logger.info({'msg': 'Failed to deposit. Too small quorum to deposit.'})
            return

        priority = self._get_deposit_priority_fee()

        logger.info({'msg': 'Sending deposit transaction.', 'values': {
            'deposit_root': str(self.deposit_root),
            'keys_op_index': str(self.keys_op_index),
            'block_number': deposit_params['block_num'],
            'block_hash': deposit_params['block_hash'].hex(),
            'signs': deposit_params['signs'],
            'gas_limit': CONTRACT_GAS_LIMIT,
            'priority_fee': priority,
        }})

        if not ACCOUNT:
            logger.info({'msg': 'Account was not provided.'})

        if not CREATE_TRANSACTIONS:
            logger.info({'msg': 'Run in dry mode'})

        try:
            result = DepositSecurityModuleInterface.depositBufferedEther(
                self.deposit_root,
                self.keys_op_index,
                deposit_params['block_num'],
                deposit_params['block_hash'],
                deposit_params['signs'],
                {
                    'gas_limit': CONTRACT_GAS_LIMIT,
                    'priority_fee': priority,
                },
            )
        except BaseException as error:
            logger.error({'msg': f'Deposit failed.', 'error': str(error)})
            DEPOSIT_FAILURE.inc()
        else:
            logger.info({'msg': f'Deposited successfully.', 'value': str(result.logs)})
            SUCCESS_DEPOSIT.inc()

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
                    CURRENT_QUORUM_SIZE.set(len(block_messages))

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
    def _get_deposit_priority_fee():
        return web3.eth.fee_history(1, 'latest', reward_percentiles=[GAS_PRIORITY_FEE_PERCENTILE])['reward'][0][0]
