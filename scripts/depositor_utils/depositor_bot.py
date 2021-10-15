from typing import List, Optional, Tuple

from brownie import interface, web3, Wei, accounts
from brownie.network.web3 import Web3

from scripts.collect_bc_deposits import (
    build_used_pubkeys_map,
)
from scripts.depositor_utils.constants import (
    LIDO_CONTRACT_ADDRESSES,
    NODE_OPS_ADDRESSES,
    DEPOSIT_CONTRACT_DEPLOY_BLOCK,
    UNREORGABLE_DISTANCE,
    EVENT_QUERY_STEP,
    DEPOSIT_SECURITY_MODULE,
    DEPOSIT_CONTRACT,
)
from scripts.depositor_utils.deposit_problems import (
    LIDO_CONTRACT_IS_STOPPED,
    NOT_ENOUGH_BALANCE_ON_ACCOUNT,
    LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER,
    LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS,
    GAS_FEE_HIGHER_THAN_RECOMMENDED,
    KEY_WAS_USED,
    DEPOSIT_SECURITY_ISSUE,
    DEPOSIT_PAUSED,
)
from scripts.depositor_utils.kafka import DepositBotMsgRecipient
from scripts.depositor_utils.logger import logger
from scripts.depositor_utils.prometheus import (
    GAS_FEE,
    OPERATORS_FREE_KEYS,
    BUFFERED_ETHER,
    DEPOSIT_FAILURE,
    LIDO_STATUS,
    SUCCESS_DEPOSIT,
    ACCOUNT_BALANCE,
)
from scripts.depositor_utils.utils import (
    as_uint256,
    sign_data,
    to_eip_2098, SignedData,
)
from scripts.depositor_utils.variables import (
    MIN_BUFFERED_ETHER,
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
        self._get_guardian_index()

        self.gas_fee_strategy = GasFeeStrategy(w3, max_gas_fee=MAX_GAS_FEE)
        self.kafka = DepositBotMsgRecipient()

        # Defaults
        self.current_block = None
        self.available_keys_to_deposit_count = 0

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

    def _get_guardian_index(self) -> Optional[int]:
        """Load account`s guardian index"""
        self.is_guardian = None

        if not self.account:
            return None

        logger.info('Load guardians and check account.')
        guardians = self.deposit_security_module.getGuardians()
        if self.account.address in guardians:
            self.is_guardian = guardians.index(self.account.address)

        logger.warning('Account is not in the guardians list.')

    def _load_constants(self):
        self.blocks_till_pause_is_valid = self.deposit_security_module.getPauseIntentValidityPeriodBlocks()
        self.max_deposits = self.deposit_security_module.getMaxDeposits()
        self.min_signs_to_deposit = self.deposit_security_module.getGuardianQuorum()

        self.deposit_prefix = self.deposit_security_module.ATTEST_MESSAGE_PREFIX()
        self.pause_prefix = self.deposit_security_module.PAUSE_MESSAGE_PREFIX()

    # ------------ CYCLE STAFF -------------------
    def run_as_daemon(self):
        """Supermega infinity cycle!"""
        while True:
            self.run_deposit_cycle()

    def run_deposit_cycle(self):
        """
        Run all pre-deposit checks. If everything is ok create transaction and push it to mempool
        """
        logger.info(f'Run deposit cycle. Block number: {self.current_block.number}')
        logger.info('Get actual chain state')
        self._update_current_block()

        # Pause message instantly if we receive pause message
        pause_messages = self.kafka.get_pause_messages(self.current_block.number, self.blocks_till_pause_is_valid)
        if pause_messages and not self.protocol_is_paused:
            self.pause_deposits_with_messages(pause_messages)

        else:
            issues = self.get_deposit_issues()
            if issues:
                self.report_issues(issues)
            else:
                self.do_deposit()

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

        # ------- Lido contract checks -------
        # Check if lido contract was stopped
        logger.info('Deposit pre checks')
        logger.info('Lido is stopped check')
        if self.lido.isStopped():
            LIDO_STATUS.state('stopped')
            deposit_issues.append(LIDO_CONTRACT_IS_STOPPED)
            logger.warning(LIDO_CONTRACT_IS_STOPPED)
        else:
            LIDO_STATUS.state('active')

        logger.info('Buffered ether check')
        # Check there is enough ether to deposit
        buffered_ether = self.lido.getBufferedEther()
        BUFFERED_ETHER.set(buffered_ether)
        if buffered_ether < MIN_BUFFERED_ETHER:
            logger.warning(LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)
            deposit_issues.append(LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)

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
        recommended_gas_fee = self.gas_fee_strategy.get_gas_fee_percentile(1, 20)
        current_gas_fee = self.current_block.baseFeePerGas

        GAS_FEE.labels('max_fee').set(MAX_GAS_FEE)
        GAS_FEE.labels('current_fee').set(current_gas_fee)
        GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)

        if recommended_gas_fee > current_gas_fee and MAX_GAS_FEE > current_gas_fee:
            logger.warning(GAS_FEE_HIGHER_THAN_RECOMMENDED)
            deposit_issues.append(GAS_FEE_HIGHER_THAN_RECOMMENDED)

        # ------- Deposit security module -------
        logger.info('Deposit security canDeposit check')
        if not self.deposit_security_module.canDeposit():
            logger.warning(DEPOSIT_SECURITY_ISSUE)
            deposit_issues.append(DEPOSIT_SECURITY_ISSUE)

        logger.info('Operators keys security check')
        operators_keys_list = self._get_unused_operators_keys()

        logger.info('Deposits not paused check')
        if self.protocol_is_paused:
            deposit_issues.append(DEPOSIT_PAUSED)
            logger.warning('Deposit contract has been paused')

        logger.info('Free keys to deposit check')
        if not operators_keys_list:
            logger.warning(LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS)
            deposit_issues.append(LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS)
        OPERATORS_FREE_KEYS.set(len(operators_keys_list))

        self.available_keys_to_deposit_count = len(operators_keys_list)

        used_keys_list = self._get_deposited_keys()

        hacked_keys = [key for key in operators_keys_list if (key in used_keys_list)]
        if hacked_keys:
            logger.error(KEY_WAS_USED)
            deposit_issues.append(KEY_WAS_USED)
            [logger.error(f'Hacked key: {key}') for key in hacked_keys]

        return deposit_issues

    def _get_unused_operators_keys(self):
        keys, signatures = self.registry.assignNextSigningKeys.call(
            self.max_deposits,
            {'from': LIDO_CONTRACT_ADDRESSES[self._web3_chain_id]},
        )

        unused_operators_keys_list = []
        for i in range(len(keys) // 48):
            unused_operators_keys_list.append(keys[i * 48: (i + 1) * 48])

        return unused_operators_keys_list

    def _get_deposited_keys(self):
        return build_used_pubkeys_map(
            # Eth2 Deposit contract block
            DEPOSIT_CONTRACT_DEPLOY_BLOCK[web3.eth.chain_id],
            self.current_block.number,
            UNREORGABLE_DISTANCE,
            EVENT_QUERY_STEP,
        )

    def report_issues(self, issues: List[str]):
        """Send statistic and send alerts for unexpected critical issues"""
        if KEY_WAS_USED in issues and DEPOSIT_PAUSED not in issues:
            self.self_pause_deposits()

    # ------------ DO DEPOSIT ------------------
    @DEPOSIT_FAILURE.count_exceptions()
    def do_deposit(self):
        """Sign and Make deposit"""
        logger.info('Start deposit')

        priority_fee = self._get_deposit_priority_fee()
        deposits_count = min(self.available_keys_to_deposit_count, self.max_deposits)

        if self.account is not None:
            logger.info('Signing deposit')
            deposit_signs = self._get_deposit_signs(self.deposit_root, self.keys_op_index)

            if len(deposit_signs) < self.min_signs_to_deposit:
                logger.warning('Not enough signs to deposit')
                return

            logger.info('Sending deposit')
            try:
                result = self.deposit_security_module.depositBufferedEther(
                    deposits_count,
                    self.deposit_root,
                    self.keys_op_index,
                    self.current_block.number,
                    self.current_block.hash,
                    deposit_signs,
                    {
                        'gas_limit': CONTRACT_GAS_LIMIT,
                        'priority_fee': priority_fee,
                    },
                )
            except BaseException as error:
                logger.error(f'Deposit failed: {error}')
            else:
                logger.info(result)

        logger.info('Deposit done')
        SUCCESS_DEPOSIT.inc()

    def _sign_deposit_message(self, deposit_root, keys_op_index) -> SignedData:
        return sign_data(
            [
                self.deposit_prefix.hex(),
                deposit_root.hex(),
                as_uint256(keys_op_index),
                as_uint256(self.current_block.number),
                self.current_block.hash.hex()[2:],
            ],
            self.account.private_key,
        )

    def _get_deposit_signs(self, deposit_root, keys_op_index) -> List[Tuple[int, int]]:
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

        signs_dict = [
            {
                'address': msg['guardianAddress'],
                'sign': (msg['signature']['r'], msg['signature']['_vs']),
            }
            for msg in sign_messages
        ]

        if self.is_guardian:
            self_sign = self._sign_deposit_message(deposit_root, keys_op_index)

            signs_dict.append({
                'address': self.account.address,
                'sign': to_eip_2098(self_sign)
            })

        sorted_signs = sorted(signs_dict, key=lambda msg: msg['address'])
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
                pause_result = self.deposit_security_module.pauseDeposits(
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
                logger.info(pause_result)

                # Cleanup kafka, no need to deposit for now
                self.kafka.clear_pause_messages()
                break

    def self_pause_deposits(self):
        """
        Pause all deposits. Use only in critical security issues.

        If None, use own sign if guardian
        """
        logger.warning('Self pause protocol initiate')

        if self.account is not None and self.is_guardian is not None:
            logger.error('Sign pause')

            # Latest block are failing on goerly !!!
            self.current_block = self._w3.eth.get_block(self.current_block.number - 1)

            pause_sign = self._sign_pause_message()

            try:
                pause_result = self.deposit_security_module.pauseDeposits(
                    self.current_block.number,
                    to_eip_2098(pause_sign),
                    {
                        'priority_fee': self._w3.eth.max_priority_fee * 2,
                    },
                )
            except BaseException as error:
                logger.error(f'Pause error: {error}')
            else:
                logger.info('Protocol was paused')
                logger.info(pause_result)
        else:
            logger.error('Guardian account is not provided')

    def _sign_pause_message(self):
        """Sign pause message"""
        return sign_data(
            [
                self.pause_prefix.hex(),
                as_uint256(self.current_block.number),
                self.current_block.hash.hex()[2:],
            ],
            self.account.private_key,
        )
