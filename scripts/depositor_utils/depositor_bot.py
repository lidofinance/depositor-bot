import time
from collections import defaultdict
from typing import List, Tuple

from brownie import interface, web3, Wei, accounts, chain
from brownie.network.web3 import Web3
from hexbytes import HexBytes
from web3.exceptions import BlockNotFound

from scripts.depositor_utils.constants import (
    LIDO_CONTRACT_ADDRESSES,
    NODE_OPS_ADDRESSES,
    DEPOSIT_SECURITY_MODULE,
    DEPOSIT_CONTRACT,
)
from scripts.depositor_utils.deposit_problems import (
    NOT_ENOUGH_BALANCE_ON_ACCOUNT,
    GAS_FEE_HIGHER_THAN_RECOMMENDED,
    DEPOSIT_SECURITY_ISSUE,
    LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER,
    LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS,
    QUORUM_IS_NOT_READY,
)
from scripts.depositor_utils.kafka import DepositBotMsgRecipient
from scripts.depositor_utils.logger import logger
from scripts.depositor_utils.prometheus import (
    GAS_FEE,
    DEPOSIT_FAILURE,
    SUCCESS_DEPOSIT,
    ACCOUNT_BALANCE,
    CURRENT_QUORUM_SIZE, BUFFERED_ETHER, OPERATORS_FREE_KEYS,
)
from scripts.depositor_utils.variables import (
    MAX_GAS_FEE,
    ACCOUNT_FILENAME,
    ACCOUNT_PRIVATE_KEY,
    CONTRACT_GAS_LIMIT, MIN_BUFFERED_ETHER, GAS_PRIORITY_FEE_PERCENTILE, GAS_FEE_PERCENTILE,
    GAS_FEE_PERCENTILE_DAYS_HISTORY,
)
from scripts.depositor_utils.gas_strategy import GasFeeStrategy


class DepositorBot:
    def __init__(self, w3: Web3):
        logger.info({'msg': 'Initialize depositor bot.'})
        self._w3 = w3
        self._web3_chain_id = self._w3.eth.chain_id

        self._load_account()
        self._load_interfaces()

        self.gas_fee_strategy = GasFeeStrategy(w3, max_gas_fee=MAX_GAS_FEE)
        self.kafka = DepositBotMsgRecipient()

        # Defaults
        self.current_block = None

        # Some rarely change things
        self._load_constants()
        logger.info({'msg': 'Depositor bot initialize done'})

    def _load_account(self):
        """Load account, that will sign and deposit"""
        if ACCOUNT_FILENAME:
            self.account = accounts.load(ACCOUNT_FILENAME)
            logger.info({'msg': 'Load account from filename.', 'value': self.account.address})

        elif ACCOUNT_PRIVATE_KEY:
            self.account = accounts.add(ACCOUNT_PRIVATE_KEY)
            logger.info({'msg': 'Load account from private key.', 'value': self.account.address})

        elif accounts:
            self.account = accounts[0]
            logger.info({'msg': 'Take first account available.', 'value': self.account.address})

        else:
            logger.warning({'msg': 'Account not provided. Run in test mode.'})
            self.account = None

    def _load_interfaces(self):
        """Load interfaces. 'from' is account by default"""
        self.lido = interface.Lido(LIDO_CONTRACT_ADDRESSES[self._web3_chain_id], owner=self.account)
        logger.info({'msg': 'Load `Lido` contract.', 'value': self.lido.address})

        self.registry = interface.NodeOperatorRegistry(NODE_OPS_ADDRESSES[self._web3_chain_id], owner=self.account)
        logger.info({'msg': 'Load `Node Operator Registry` contract.', 'value': self.registry.address})

        self.deposit_security_module = interface.DepositSecurityModule(DEPOSIT_SECURITY_MODULE[self._web3_chain_id], owner=self.account)
        logger.info({'msg': 'Load `Deposit Security` contract.', 'value': self.deposit_security_module.address})

        self.deposit_contract = interface.DepositContract(DEPOSIT_CONTRACT[self._web3_chain_id], owner=self.account)
        logger.info({'msg': 'Load `Deposit` contract.', 'value': self.deposit_contract.address})

    def _load_constants(self):
        self.blocks_till_pause_is_valid = self.deposit_security_module.getPauseIntentValidityPeriodBlocks()
        logger.info({
            'msg': f'Call `getPauseIntentValidityPeriodBlocks()`.',
            'value': self.blocks_till_pause_is_valid
        })

        self.min_signs_to_deposit = self.deposit_security_module.getGuardianQuorum()
        logger.info({'msg': f'Call `getGuardianQuorum()`.', 'value': self.min_signs_to_deposit})

        self.deposit_prefix = self.deposit_security_module.ATTEST_MESSAGE_PREFIX()
        logger.info({'msg': 'Call `ATTEST_MESSAGE_PREFIX()`.', 'value': str(self.deposit_prefix)})

        self.pause_prefix = self.deposit_security_module.PAUSE_MESSAGE_PREFIX()
        logger.info({'msg': 'Call `PAUSE_MESSAGE_PREFIX()`.', 'value': str(self.pause_prefix)})

    # ------------ CYCLE STAFF -------------------
    def run_as_daemon(self):
        """Super-Mega infinity cycle!"""
        while True:
            try:
                for _ in chain.new_blocks():
                    self.run_deposit_cycle()
            except BlockNotFound as error:
                logger.warning({'msg': 'Fetch block exception (BlockNotFound)', 'error': str(error)})

    def run_deposit_cycle(self):
        """
        Fetch latest signs from
        """
        logger.info({'msg': 'New deposit cycle.'})
        self._update_current_block()

        # Pause message instantly if we receive pause message
        pause_messages = self.kafka.get_pause_messages(self.current_block.number, self.blocks_till_pause_is_valid)
        deposit_issues = self.get_deposit_issues()

        if not self.protocol_is_paused:
            if pause_messages:
                self.pause_deposits_with_messages(pause_messages)

            elif not deposit_issues:
                self.do_deposit()

            # elif DEPOSIT_SECURITY_ISSUE in deposit_issues:
            #     time.sleep(600)
            #
            # elif NOT_ENOUGH_BALANCE_ON_ACCOUNT in deposit_issues:
            #     time.sleep(300)
        else:
            logger.info({'msg': 'Protocol was paused. Sleep for 3 minutes.'})
            time.sleep(180)

    def _update_current_block(self):
        self.current_block = self._w3.eth.get_block('latest')
        logger.info({'msg': f'Fetch `latest` block.', 'value': self.current_block.number})

        self.protocol_is_paused = self.deposit_security_module.isPaused()
        logger.info({'msg': f'Call `isPaused()`.', 'value': self.protocol_is_paused})

        self.deposit_root = self.deposit_contract.get_deposit_root()
        logger.info({'msg': f'Call `get_deposit_root()`.', 'value': str(self.deposit_root)})

        self.keys_op_index = self.registry.getKeysOpIndex()
        logger.info({'msg': f'Call `getKeysOpIndex()`.', 'value': self.keys_op_index})

        self.kafka.update_messages()

    # ------------- FIND ISSUES -------------------
    def get_deposit_issues(self) -> List[str]:
        """Do a lot of checks and send all things why deposit could not be done"""
        deposit_issues = []

        # ------- Other checks -------
        if self.account:
            balance = web3.eth.get_balance(self.account.address)
            ACCOUNT_BALANCE.set(balance)
            if balance < Wei('0.01 ether'):
                logger.error({'msg': NOT_ENOUGH_BALANCE_ON_ACCOUNT})
                deposit_issues.append(NOT_ENOUGH_BALANCE_ON_ACCOUNT)

                logger.warning({'msg': 'Account balance is low.', 'value': balance})

            else:
                logger.info({'msg': 'Check account balance.', 'value': balance})

        else:
            logger.info({'msg': '[DRY] Check account balance.', 'value': 0})
            ACCOUNT_BALANCE.set(0)

        # Gas price check
        recommended_gas_fee = self.gas_fee_strategy.get_gas_fee_percentile(
            GAS_FEE_PERCENTILE_DAYS_HISTORY,
            GAS_FEE_PERCENTILE,
        )
        current_gas_fee = self.current_block.baseFeePerGas

        GAS_FEE.labels('max_fee').set(MAX_GAS_FEE)
        GAS_FEE.labels('current_fee').set(current_gas_fee)
        GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)

        logger.info({'msg': 'Fetch gas fees.', 'values': {
            'max_fee': MAX_GAS_FEE,
            'current_fee': current_gas_fee,
            'recommended_fee': recommended_gas_fee,
        }})

        if current_gas_fee > MAX_GAS_FEE or current_gas_fee > recommended_gas_fee:
            logger.warning({
                'msg': GAS_FEE_HIGHER_THAN_RECOMMENDED,
                'values': {
                    'max_fee': MAX_GAS_FEE,
                    'current_fee': current_gas_fee,
                    'recommended_fee': recommended_gas_fee,
                }
            })
            deposit_issues.append(GAS_FEE_HIGHER_THAN_RECOMMENDED)

        can_deposit = self.deposit_security_module.canDeposit()
        logger.info({'msg': 'Call `canDeposit()`.', 'value': can_deposit})
        if not can_deposit:
            logger.warning({'msg': 'Deposit security module prohibits deposits.', 'value': can_deposit})
            deposit_issues.append(DEPOSIT_SECURITY_ISSUE)

        # Lido contract buffered ether check
        buffered_ether = self.lido.getBufferedEther()
        logger.info({'msg': 'Call `getBufferedEther()`.', 'value': buffered_ether})
        BUFFERED_ETHER.set(buffered_ether)
        if buffered_ether < MIN_BUFFERED_ETHER:
            logger.warning({'msg': LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER, 'value': buffered_ether})
            deposit_issues.append(LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)

        # Check that contract has unused operators keys
        free_keys = self._get_operators_free_keys_count()
        OPERATORS_FREE_KEYS.set(free_keys)
        logger.info({'msg': 'Call `getNodeOperator()` and `getNodeOperatorsCount()`. Value is free keys', 'value': free_keys})

        if not free_keys:
            logger.warning({'msg': LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS, 'value': free_keys})
            deposit_issues.append(LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS)

        # Check all signs
        # self._get_deposit_params()
        signs = self._get_deposit_params(self.deposit_root, self.keys_op_index)
        if signs is None:
            logger.warning({'msg': QUORUM_IS_NOT_READY})
            deposit_issues.append(QUORUM_IS_NOT_READY)

        return deposit_issues

    def _get_operators_free_keys_count(self):
        operators_data = [{**self.registry.getNodeOperator(i, True), **{'index': i}} for i in range(self.registry.getNodeOperatorsCount())]

        free_keys = 0

        for operator in operators_data:
            free_keys += self._get_operator_free_keys_count(operator)

        OPERATORS_FREE_KEYS.set(free_keys)

        return free_keys

    def _get_operator_free_keys_count(self, operator: dict) -> int:
        """Check if operator has free keys"""
        free_space = operator['stakingLimit'] - operator['usedSigningKeys']
        keys_to_deposit = operator['totalSigningKeys'] - operator['usedSigningKeys']
        return min(free_space, keys_to_deposit)

    # ------------ DO DEPOSIT ------------------
    def do_deposit(self):
        """Sign and Make deposit"""
        logger.info({'msg': 'No issues found. Try to deposit.'})
        deposit_params = self._get_deposit_params(self.deposit_root, self.keys_op_index)

        if self.account is not None and deposit_params:
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

            try:
                result = self.deposit_security_module.depositBufferedEther(
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
        elif self.account is None and deposit_params:
            logger.info({'msg': '[DRY] No account provided. Deposit done.'})
        else:
            logger.info({'msg': 'Failed to deposit. Too small quorum to deposit.'})

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
            block_number=self.current_block.number,
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

    def _from_messages_to_signs(self, messages) -> List[Tuple[int, int]]:
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

    def _get_deposit_priority_fee(self):
        # TODO: fix this
        # max_priority_fee = self._w3.eth.max_priority_fee * 1.25
        # transactions = self._w3.eth.get_block('pending').transactions
        # for transaction in transactions:
        #     if transaction.to == DEPOSIT_CONTRACT[self._web3_chain_id]:
        #         max_priority_fee = max(max_priority_fee, transaction.priority_fee)
        # return max_priority_fee + 1
        return self._w3.eth.fee_history(1, 'latest', reward_percentiles=[GAS_PRIORITY_FEE_PERCENTILE])['reward'][0][0]

    # ----------- DO PAUSE ----------------
    def pause_deposits_with_messages(self, messages: List[dict]):
        logger.warning({'msg': 'Message pause protocol initiate.', 'value': messages})
        for message in messages:
            priority_fee = self._w3.eth.max_priority_fee * 2

            logger.info({
                'msg': 'Send pause transaction.',
                'values': {
                    'block_number': message['blockNumber'],
                    'signature': (message['signature']['r'], message['signature']['_vs']),
                    'priority_fee': priority_fee,
                },
            })

            try:
                result = self.deposit_security_module.pauseDeposits(
                    message['blockNumber'],
                    (message['signature']['r'], message['signature']['_vs']),
                    {
                        'priority_fee': priority_fee,
                    },
                )
            except BaseException as error:
                logger.error({'msg': f'Pause error.', 'error': str(error), 'value': message})
            else:
                logger.warning({'msg': 'Protocol was paused', 'value': str(result.logs)})

                # Cleanup kafka, no need to deposit for now
                self.kafka.clear_pause_messages()
                break
