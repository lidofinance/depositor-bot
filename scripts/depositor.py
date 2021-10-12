from typing import Optional, List, Tuple

import numpy
from brownie import accounts, chain, interface, web3, Wei
from brownie.network.account import LocalAccount
from brownie.network.web3 import Web3
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
    YAY_PREFIX,
    NAY_PREFIX
)
from scripts.depositor_utils.deposit_problems import (
    LIDO_CONTRACT_IS_STOPPED,
    NOT_ENOUGH_BALANCE_ON_ACCOUNT,
    LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER,
    LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS,
    GAS_FEE_HIGHER_THAN_RECOMMENDED,
    KEY_WAS_USED,
    DEPOSIT_SECURITY_ISSUE,
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
    keccak256_hash,
    as_bytes32,
    as_uint256,
    ecdsa_sign,
    SignedData,
)
from scripts.depositor_utils.variables import (
    MIN_BUFFERED_ETHER,
    MAX_GAS_FEE,
    ACCOUNT_FILENAME,
    ACCOUNT_PRIVATE_KEY,
    CONTRACT_GAS_LIMIT,
)


def main():
    logger.info('Start up metrics service on port: 8080.')
    start_http_server(8080)

    # sign_frontrun_protection_yay_data = partial(
    #     sign_frontrun_protection_data, YAY_PREFIX
    # )
    # sign_frontrun_protection_nay_data = partial(
    #     sign_frontrun_protection_data, NAY_PREFIX
    # )

    # PAUSE_MESSAGE_PREFIX = deposit_security_module.ATTEST_MESSAGE_PREFIX.call()
    # PAUSE_MESSAGE_PREFIX = deposit_security_module.PAUSE_MESSAGE_PREFIX.call()

    # deposit_root, keys_op_index = get_frontrun_protection_data(deposit_contract, registry)
    #
    # yay_data = sign_frontrun_protection_yay_data(
    #     self_index,
    #     as_bytes32(deposit_root),
    #     as_uint256(keys_op_index)
    # )
    # deposit_buffered_ether(account, lido, signing_keys_list, yay_data)
    #
    # nay_data = sign_frontrun_protection_nay_data(
    #     self_index,
    #     as_uint256(current_block),
    # )
    #
    # def get_frontrun_protection_data(deposit_contract, registry):
    #     deposit_root = deposit_contract.get_deposit_root()
    #     key_ops_index = 0  # registry.getKeysOpIndex()
    #     return deposit_root, key_ops_index
    #
    #
    # def sign_frontrun_protection_data(
    #         prefix, self_index, *data
    # ) -> Optional[Tuple[SignedData, int]]:
    #     signed_data = sign_data([prefix, *data])
    #     if signed_data is None:
    #         return None
    #     return signed_data, self_index
    #
    #
    # def sign_data(data) -> Optional[SignedData]:
    #     private_key = get_private_key()
    #     if private_key is None:
    #         return None
    #     hashed = keccak256_hash(''.join(data))
    #     signed = ecdsa_sign(hashed, private_key)
    #     return signed


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
        self.current_block = 0
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
        guardians = self.deposit_security_module.getGuardians().call()
        if self.account.address in guardians:
            return guardians.index(self.account.address)

        logger.warning('Account is not in the guardians list.')
        raise AssertionError('Account is not permitted to do deposits.')

    def run_deposit_cycle(self):
        """
        Run all pre-deposit checks. If everything is ok create transaction and push it to mempool
        """
        self.current_block = web3.eth.block_number
        logger.info(f'Run deposit cycle. Block number: {self.current_block}')

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
        if self.lido.isStoppend():
            deposit_issues.append(LIDO_CONTRACT_IS_STOPPED)
            logger.warning(LIDO_CONTRACT_IS_STOPPED)

        # Check there is enough ether to deposit
        buffered_ether = self.lido.getBufferedEther()
        BUFFERED_ETHER.set(buffered_ether)
        if buffered_ether < MIN_BUFFERED_ETHER:
            logger.warning(LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)
            deposit_issues.append(LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)

        if not self._has_free_keys_to_deposit():
            logger.warning(LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS)
            deposit_issues.append(LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS)

        # ------- Other checks -------
        if self.account:
            balance = web3.eth.get_balance(self.account.address)
            ACCOUNT_BALANCE.set(balance)
            if balance < Wei('0.01 ether'):
                logger.error(NOT_ENOUGH_BALANCE_ON_ACCOUNT)
                deposit_issues.append(NOT_ENOUGH_BALANCE_ON_ACCOUNT)
        else:
            ACCOUNT_BALANCE.set(0)

        # Gas price check
        recommended_gas_fee = self.gas_fee_strategy.get_gas_fee_percentile(1, 20)
        current_gas_fee = self._w3.eth.get_block('latest').baseFeePerGas

        GAS_FEE.labels('max_fee').set(MAX_GAS_FEE)
        GAS_FEE.labels('current_fee').set(current_gas_fee)
        GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)

        if recommended_gas_fee > current_gas_fee and MAX_GAS_FEE > current_gas_fee:
            logger.warning(GAS_FEE_HIGHER_THAN_RECOMMENDED)
            deposit_issues.append(GAS_FEE_HIGHER_THAN_RECOMMENDED)

        # ------- Deposit security module -------
        if self.deposit_security_module.canDeposit():
            logger.warning(DEPOSIT_SECURITY_ISSUE)
            deposit_issues.append(DEPOSIT_SECURITY_ISSUE)

        operators_keys_list = self._get_unused_operators_keys()
        self.available_keys_to_deposit_count = len(operators_keys_list)

        used_keys_list = self._get_deposited_keys()

        hacked_keys = [key for key in operators_keys_list if (key in used_keys_list)]
        if hacked_keys:
            # TODO: somehow report hacked keys
            logger.error(KEY_WAS_USED)
            deposit_issues.append(KEY_WAS_USED)

        # TODO:
        # getPauseIntentValidityPeriodBlocks - till this block. What is it?
        # getGuardianCourm - check that signs count is ok to deposit. No need now because there will be only one.
        return deposit_issues

    def _has_free_keys_to_deposit(self):
        """Return free keys count that could be deposited"""
        operators_data = [{
            **self.registry.getNodeOperator(i, True),
            **{'index': i}
        } for i in range(self.registry.getNodeOperatorsCount())]

        free_keys = 0

        for operator in operators_data:
            free_keys += self._get_operator_free_keys_count(operator)

        OPERATORS_FREE_KEYS.set(free_keys)

        return bool(free_keys)

    @staticmethod
    def _get_operator_free_keys_count(operator: dict) -> int:
        """Check if operator has free keys"""
        free_space = operator['stakingLimit'] - operator['usedSigningKeys']
        keys_to_deposit = operator['totalSigningKeys'] - operator['usedSigningKeys']
        return min(free_space, keys_to_deposit)

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
            self.current_block,
            UNREORGABLE_DISTANCE,
            EVENT_QUERY_STEP,
        )

    def report_issues(self, issues: List[str]):
        """Send statistic and send alerts for unexpected critical issues"""
        if KEY_WAS_USED in issues:
            self.pause_deposits()

    @DEPOSIT_FAILURE.count_exceptions()
    def do_deposit(self):
        """Sign and Make deposit"""
        max_deposits = self.deposit_security_module.getMaxDeposits()

        deposits_count = min(self.available_keys_to_deposit_count, max_deposits)

        self.deposit_security_module.depositBufferedEther(
            deposits_count,
            # TODO: DEPOSIT ROOT
            ['signature'],
            {'gas_limit': CONTRACT_GAS_LIMIT},
        )
        SUCCESS_DEPOSIT.inc()

    def pause_deposits(self):
        """Pause all deposits. Use only in critical security issues"""
        priority_fee = self._w3.eth.max_priority_fee * 2

        self.deposit_security_module.Pause(
            self.current_block,
            'signature',  # TODO: SIG
            {'priority_fee': priority_fee},
        )


class GasFeeStrategy:
    BLOCKS_IN_ONE_DAY = 6600
    LATEST_BLOCK = 'latest'

    def __init__(self, w3: Web3, blocks_count_cache: int = 7800, max_gas_fee: int = None):
        """
        gas_history_block_cache - blocks count that gas his
        """
        self._w3 = w3
        self._blocks_count_cache: int = blocks_count_cache
        self._latest_fetched_block: int = 0
        self._gas_fees: list = []
        self.max_gas_fee = max_gas_fee

    def _fetch_gas_fee_history(self, days):
        """
        Returns gas fee history for N days.
        Cache updates every {_blocks_count_cache} block.
        """
        latest_block_num = self._w3.eth.get_block('latest')['number']

        # If _blocks_count_cache didn't passed return cache
        if self._latest_fetched_block and self._latest_fetched_block + self._blocks_count_cache > latest_block_num:
            return self._gas_fees

        total_blocks_to_fetch = self.BLOCKS_IN_ONE_DAY * days
        requests_count = total_blocks_to_fetch // days + 1

        gas_fees = []
        last_block = self.LATEST_BLOCK

        for i in range(requests_count):
            stats = self._w3.eth.fee_history(1024, last_block)
            last_block = stats['oldestBlock'] - 2
            gas_fees = stats['baseFeePerGas'] + gas_fees

        self._gas_fees = gas_fees
        self._last_gas_fee_block = self._w3.eth.get_block('latest')['number']

        return self._gas_fees

    def get_gas_fee_percentile(self, days: int, percentile: int):
        """Finds """
        # One week price stats
        gas_fee_history = self._fetch_gas_fee_history(days)
        return numpy.percentile(gas_fee_history, percentile)
