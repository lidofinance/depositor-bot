from collections import defaultdict
from typing import List, Tuple

from brownie import interface, web3, Wei, accounts, chain
from brownie.network.web3 import Web3
from hexbytes import HexBytes

from scripts.depositor_utils.constants import (
    LIDO_CONTRACT_ADDRESSES,
    NODE_OPS_ADDRESSES,
    DEPOSIT_SECURITY_MODULE,
    DEPOSIT_CONTRACT,
)
from scripts.depositor_utils.deposit_problems import (
    NOT_ENOUGH_BALANCE_ON_ACCOUNT,
    GAS_FEE_HIGHER_THAN_RECOMMENDED,
)
from scripts.depositor_utils.kafka import DepositBotMsgRecipient
from scripts.depositor_utils.logger import logger
from scripts.depositor_utils.prometheus import (
    GAS_FEE,
    DEPOSIT_FAILURE,
    SUCCESS_DEPOSIT,
    ACCOUNT_BALANCE,
)
from scripts.depositor_utils.variables import (
    MAX_GAS_FEE,
    ACCOUNT_FILENAME,
    ACCOUNT_PRIVATE_KEY,
    CONTRACT_GAS_LIMIT,
)
from scripts.depositor_utils.gas_strategy import GasFeeStrategy


class DepositorBot:
    def __init__(self, w3: Web3):
        logger.info('Init depositor bot.')
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

    def _load_account(self):
        """Load account, that will sign and deposit"""
        if ACCOUNT_FILENAME:
            logger.info('Load account from filename.')
            self.account = accounts.load(ACCOUNT_FILENAME)

        elif ACCOUNT_PRIVATE_KEY:
            logger.info('Load account from private key.')
            self.account = accounts.add(ACCOUNT_PRIVATE_KEY)

        elif accounts:
            logger.info('Take first account available.')
            self.account = accounts[0]

        else:
            logger.warning('Account not provided. Run in test mode.')
            self.account = None

    def _load_interfaces(self):
        """Load interfaces. 'from' is account by default"""
        logger.info('Get Lido contract.')
        self.lido = interface.Lido(LIDO_CONTRACT_ADDRESSES[self._web3_chain_id], owner=self.account)

        logger.info('Get Node Operator Registry contract.')
        self.registry = interface.NodeOperatorRegistry(NODE_OPS_ADDRESSES[self._web3_chain_id], owner=self.account)

        logger.info('Get Deposit Security module contract.')
        self.deposit_security_module = interface.DepositSecurityModule(DEPOSIT_SECURITY_MODULE[self._web3_chain_id], owner=self.account)

        logger.info('Get Deposit contract.')
        self.deposit_contract = interface.DepositContract(DEPOSIT_CONTRACT[self._web3_chain_id], owner=self.account)

    def _load_constants(self):
        self.blocks_till_pause_is_valid = self.deposit_security_module.getPauseIntentValidityPeriodBlocks()
        self.max_deposits = self.deposit_security_module.getMaxDeposits()
        self.min_signs_to_deposit = self.deposit_security_module.getGuardianQuorum()

        self.deposit_prefix = self.deposit_security_module.ATTEST_MESSAGE_PREFIX()
        self.pause_prefix = self.deposit_security_module.PAUSE_MESSAGE_PREFIX()

    # ------------ CYCLE STAFF -------------------
    def run_as_daemon(self):
        """Super-Mega infinity cycle!"""
        for _ in chain.new_blocks():
            self.run_deposit_cycle()

    def run_deposit_cycle(self):
        """
        Fetch latest signs from
        """
        self._update_current_block()
        logger.info(f'Run deposit cycle. Block number: {self.current_block.number}')
        logger.info('Get actual chain state')

        # Pause message instantly if we receive pause message
        pause_messages = self.kafka.get_pause_messages(self.current_block.number, self.blocks_till_pause_is_valid)

        if not self.protocol_is_paused:
            if pause_messages:
                self.pause_deposits_with_messages(pause_messages)
            elif not self.get_deposit_issues():
                self.do_deposit()
        else:
            logger.warning('Protocol paused')

    def _update_current_block(self):
        self.current_block = self._w3.eth.get_block('latest')
        self.deposit_root = self.deposit_contract.get_deposit_root()
        self.keys_op_index = self.registry.getKeysOpIndex()
        self.kafka.update_messages()
        self.protocol_is_paused = self.deposit_security_module.isPaused()

    # ------------- FIND ISSUES -------------------
    def get_deposit_issues(self) -> List[str]:
        """Do a lot of checks and send all things why deposit could not be done"""
        deposit_issues = []

        # ------- Other checks -------
        logger.info('Account balance check')
        if self.account:
            balance = web3.eth.get_balance(self.account.address)
            ACCOUNT_BALANCE.set(balance)
            if balance < Wei('0.01 ether'):
                logger.error(NOT_ENOUGH_BALANCE_ON_ACCOUNT)
                deposit_issues.append(NOT_ENOUGH_BALANCE_ON_ACCOUNT)
        else:
            ACCOUNT_BALANCE.set(0)

        logger.info('Recommended gas fee check')
        # Gas price check
        recommended_gas_fee = self.gas_fee_strategy.get_gas_fee_percentile(15, 30)
        current_gas_fee = self.current_block.baseFeePerGas

        GAS_FEE.labels('max_fee').set(MAX_GAS_FEE)
        GAS_FEE.labels('current_fee').set(current_gas_fee)
        GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)

        if recommended_gas_fee > current_gas_fee and MAX_GAS_FEE > current_gas_fee:
            logger.warning(GAS_FEE_HIGHER_THAN_RECOMMENDED)
            deposit_issues.append(GAS_FEE_HIGHER_THAN_RECOMMENDED)

        return deposit_issues

    # ------------ DO DEPOSIT ------------------
    def do_deposit(self):
        """Sign and Make deposit"""
        logger.info('Start deposit')
        logger.info('Get deposit params')
        deposit_params = self._get_deposit_params(self.deposit_root, self.keys_op_index)

        if self.account is not None and deposit_params:
            logger.info('Sending deposit transaction')
            try:
                self.deposit_security_module.depositBufferedEther(
                    self.deposit_root,
                    self.keys_op_index,
                    deposit_params['block_num'],
                    deposit_params['block_hash'],
                    deposit_params['signs'],
                    {
                        'gas_limit': CONTRACT_GAS_LIMIT,
                        'priority_fee': self._get_deposit_priority_fee(),
                        'max_fee': self.gas_fee_strategy.get_gas_fee_percentile(15, 50),
                    },
                )
            except BaseException as error:
                logger.error(f'Deposit failed: {error}')
                DEPOSIT_FAILURE.inc()
            else:
                logger.info(f'Success deposit')

        logger.info('Deposit done')
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
            block_number=self.current_block.number,
            deposit_root=deposit_root,
            keys_op_index=keys_op_index,
        )

        dict_for_sort = defaultdict(lambda: defaultdict(list))

        for message in sign_messages:
            dict_for_sort[message['blockNumber']][message['blockHash']].append(message)

        for block_num, blocks_by_number in dict_for_sort.items():
            for block_hash, block_messages in blocks_by_number.items():
                if len(block_messages) >= self.min_signs_to_deposit:
                    # Take the oldest messages to prevent reorganizations
                    return {
                        'signs': self._from_messages_to_signs(block_messages),
                        'block_num': block_num,
                        'block_hash': HexBytes(block_hash),
                    }

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
        return self._w3.eth.fee_history(1, 'latest', reward_percentiles=[50])['reward'][0][0]

    # ----------- DO PAUSE ----------------
    def pause_deposits_with_messages(self, messages: List[dict]):
        logger.warning('Message pause protocol initiate')
        for message in messages:
            try:
                self.deposit_security_module.pauseDeposits(
                    message['blockNumber'],
                    (message['signature']['r'], message['signature']['_vs']),
                    {
                        'priority_fee': self._w3.eth.max_priority_fee * 2,
                    },
                )
            except BaseException as error:
                logger.error(f'Pause error: {error}')
                logger.error(f'Message: {message}')
            else:
                logger.info('Protocol was paused')

                # Cleanup kafka, no need to deposit for now
                self.kafka.clear_pause_messages()
                break
