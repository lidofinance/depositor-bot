from typing import List

from brownie import interface, web3, Wei, accounts
from brownie.network.web3 import Web3
from kafka import KafkaConsumer, KafkaProducer
from prometheus_client.exposition import start_http_server

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
    to_eip_2098,
)
from scripts.depositor_utils.variables import (
    MIN_BUFFERED_ETHER,
    MAX_GAS_FEE,
    ACCOUNT_FILENAME,
    ACCOUNT_PRIVATE_KEY,
    CONTRACT_GAS_LIMIT,
)
from scripts.depositor_utils.gas_strategy import GasFeeStrategy


def main():
    logger.info('Start up metrics service on port: 8080.')
    start_http_server(8080)
    depositor_bot = DepositorBot(web3)
    # depositor_bot.run_as_daemon()

    # Just for tests
    depositor_bot._update_current_block()
    depositor_bot.do_deposit()



class DepositorBot:
    def __init__(self, w3: Web3):
        logger.info('Init depositor bot.')
        self._w3 = w3
        self._web3_chain_id = self._w3.eth.chain_id

        self._load_account()
        self._load_interfaces()
        self._guardian_index = self._get_guardian_index()

        self.gas_fee_strategy = GasFeeStrategy(w3, max_gas_fee=MAX_GAS_FEE)

        # Defaults
        self.current_block = None
        self.available_keys_to_deposit_count = 0

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

    def _get_guardian_index(self):
        if not self.account:
            return 0

        logger.info('Load guardians and check account.')
        guardians = self.deposit_security_module.getGuardians()
        if self.account.address in guardians:
            return guardians.index(self.account.address)

        logger.warning('Account is not in the guardians list.')
        raise AssertionError('Account is not permitted to do deposits.')

    def run_as_daemon(self):
        while True:
            self.run_deposit_cycle()

    def run_deposit_cycle(self):
        """
        Run all pre-deposit checks. If everything is ok create transaction and push it to mempool
        """
        self._update_current_block()
        logger.info(f'Run deposit cycle. Block number: {self.current_block.number}')

        issues = self.get_deposit_issues()
        if issues:
            self.report_issues(issues)
        else:
            self.do_deposit()

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
        if self.deposit_security_module.isPaused():
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
            # TODO: somehow report hacked keys
            logger.error(KEY_WAS_USED)
            deposit_issues.append(KEY_WAS_USED)

        return deposit_issues

    def _get_unused_operators_keys(self):
        max_deposits = self.deposit_security_module.getMaxDeposits()

        keys, signatures = self.registry.assignNextSigningKeys.call(
            max_deposits,
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
            self.pause_deposits()

    @DEPOSIT_FAILURE.count_exceptions()
    def do_deposit(self):
        """Sign and Make deposit"""

        logger.info('Start deposit')
        max_deposits = self.deposit_security_module.getMaxDeposits()

        priority_fee = self._get_deposit_priority_fee()
        deposits_count = min(self.available_keys_to_deposit_count, max_deposits)

        if self.account is not None:
            logger.info('Signing deposit')

            deposit_signs = self._get_deposit_signs(self.deposit_root, self.keys_op_index)

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

    def _update_current_block(self):
        self.current_block = self._w3.eth.get_block('latest')
        self.deposit_root = self.deposit_contract.get_deposit_root()
        self.keys_op_index = self.registry.getKeysOpIndex()

    def _sign_deposit_message(self, deposit_root, keys_op_index):
        deposit_prefix = self.deposit_security_module.ATTEST_MESSAGE_PREFIX()

        return sign_data(
            [
                deposit_prefix.hex(),
                deposit_root.hex(),
                as_uint256(keys_op_index),
                as_uint256(self.current_block.number),
                self.current_block.hash.hex()[2:],
            ],
            self.account.private_key,
        )

    def _get_deposit_signs(self, deposit_root, keys_op_index):
        """
        Get all signs from kafka.
        Make sure they are from one block_num.
        Check sign count is enough for deposit.
        Generate own sign.
        Return signs.
        """
        signs = []
        # With kafka add messages
        consumer = KafkaConsumer(
            'goerli-defender',
            client_id='random',
            group_id='goerli-defender-group',
            security_protocol='SSL',
            bootstrap_servers='pkc-l7q2j.europe-north1.gcp.confluent.cloud:9092',
            sasl_mechanism='PLAIN',
            sasl_plain_username='RIHLD36EHYTHQG5W',
            sasl_plain_password='qv4EBFsbl1aKT4VTiczxvGxhb4AO1pH5ne6PdW2HqvHJTZVz/BfJlqEKw1Ft7ZDM',
        )
        for msg in consumer:
            print(msg.value)

        return signs

    def _get_deposit_priority_fee(self):
        # TODO: fix this
        # max_priority_fee = self._w3.eth.max_priority_fee * 1.25
        # transactions = self._w3.eth.get_block('pending').transactions
        # for transaction in transactions:
        #     if transaction.to == DEPOSIT_CONTRACT[self._web3_chain_id]:
        #         max_priority_fee = max(max_priority_fee, transaction.priority_fee)
        # return max_priority_fee + 1

        return self._w3.eth.fee_history(1, 'latest', reward_percentiles=[50])['reward'][0][0]

    def pause_deposits(self):
        """
        Pause all deposits. Use only in critical security issues.
        """
        logger.info('Pause protocol')

        logger.info('Update last block info')

        blocks_till_pause_is_valid = self.deposit_security_module.getPauseIntentValidityPeriodBlocks()
        if self._w3.eth.block_number <= self.current_block.number + blocks_till_pause_is_valid:
            logger.error('Pause started')

            if self.account is not None:
                logger.error('Sign pause')

                # Latest block are failing on goerly !!!
                self.current_block = self._w3.eth.get_block(self.current_block.number - 1)

                pause_sign = self._sign_pause_message()

                try:
                    pause_result = self.deposit_security_module.pauseDeposits(
                        self.current_block.number,
                        self.current_block.hash,
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
            logger.error('Pause is not valid any more')

    def _sign_pause_message(self):
        pause_prefix = self.deposit_security_module.PAUSE_MESSAGE_PREFIX()

        return sign_data(
            [
                pause_prefix.hex(),
                as_uint256(self.current_block.number),
                self.current_block.hash.hex()[2:],
            ],
            self.account.private_key,
        )
