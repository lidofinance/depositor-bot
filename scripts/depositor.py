import time
from typing import Optional, List, Tuple

import numpy
from brownie import accounts, chain, interface, web3, Wei
from brownie.network.account import LocalAccount
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
    GAS_FEE_HIGHER_THAN_TRESHOLD,
    GAS_FEE_HIGHER_THAN_RECOMMENDED,
    KEY_WAS_USED,
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
from scripts.depositor_utils.utils import cache
from scripts.depositor_utils.variables import (
    MIN_BUFFERED_ETHER,
    MAX_GAS_FEE,
    ACCOUNT_FILENAME,
    ACCOUNT_PRIVATE_KEY,
    DEPOSIT_AMOUNT,
    CONTRACT_GAS_LIMIT,
    GAS_PREDICTION_PERCENTILE,
)


def get_account() -> Optional[LocalAccount]:
    if ACCOUNT_FILENAME:
        logger.info('Load account from filename.')
        return accounts.load(ACCOUNT_FILENAME)

    if ACCOUNT_PRIVATE_KEY:
        logger.info('Load account from private key.')
        return accounts.add(ACCOUNT_PRIVATE_KEY)

    if accounts:
        logger.info('Take first account available.')
        return accounts[0]

    # Only for testing propose
    logger.warning('Account not provided. Run in test mode.')


def main():
    # Prometheus
    logger.info('Start deposit bot.')
    start_http_server(8080)

    logger.info('Load account.')
    account = get_account()

    eth_chain_id = web3.eth.chain_id

    lido = interface.Lido(LIDO_CONTRACT_ADDRESSES[eth_chain_id], owner=account)
    registry = interface.NodeOperators(NODE_OPS_ADDRESSES[eth_chain_id], owner=account)
    #todo merge into 1 nop registry
    upgraded_registry = interface.NodeOperatorRegistry(NODE_OPS_ADDRESSES[eth_chain_id], owner=account)
    deposit_security_module = interface.DepositSecurityModule(DEPOSIT_SECURITY_MODULE[eth_chain_id], owner=account)

    deposit_contract = interface.DepositContract(DEPOSIT_CONTRACT[web3.eth.chain_id])

    ATTEST_MESSAGE_PREFIX = bytes.fromhex("1085395a994e25b1b3d0ea7937b7395495fb405b31c7d22dbc3976a6bd01f2bf") #deposit_security_module.ATTEST_MESSAGE_PREFIX.call()
    PAUSE_MESSAGE_PREFIX = bytes.fromhex("1085395a994e25b1b3d0ea7937b7395495fb405b31c7d22dbc3976a6bd01f2bf") #deposit_security_module.PAUSE_MESSAGE_PREFIX.call()

    self_index = get_self_index(deposit_security_module, account)


    while True:
        logger.info('New deposit cycle.')

        current_block = web3.eth.block_number
        (deposit_root, keys_op_index) = get_frontrun_protection_data(deposit_contract, upgraded_registry)

        problems, signing_keys_list = get_deposit_problems(account, lido, registry, eth_chain_id)
        if not problems:
            try:
                logger.info(f'Try to deposit.')
                fp_attest_data = frontrun_protection_attest_data(ATTEST_MESSAGE_PREFIX, deposit_root, keys_op_index, self_index)
                deposit_buffered_ether(account, lido, signing_keys_list, fp_attest_data)
            except Exception as error:
                logger.error(str(error))
                time.sleep(15)
        elif KEY_WAS_USED in problems:
            fp_pause_data = frontrun_protection_pause_data(PAUSE_MESSAGE_PREFIX, current_block)
            pause_deposits(deposit_security_module, self_index, fp_pause_data)
        else:
            logger.info(f'Deposit cancelled. Problems count: {len(problems)}')
            time.sleep(15)

#TODO not implemented
def get_self_index(deposit_security_module, account):
    if not account:
        logger.info('Account not provided, assuming self index is 0 for testing purpose.')
        return 0
    else:
        #todo test
        guardians = deposit_security_module.getGuardians().call()
        if account in guardians:
            return guardians.index(account)
        else:
            logger.warning('Account is not in the guardians list.')
            #todo error handling
            return 0

def get_frontrun_protection_data(deposit_contract, registry):
    deposit_root = deposit_contract.get_deposit_root()
    key_ops_index = 0 #registry.getKeysOpIndex()
    return (deposit_root, key_ops_index)

def sign_data(data):
    return 0

def sign_frontrun_protection_yay_data(self_index, dd_root, nos_index):
    return sign_data([yay_prefix, dd_root, nos_index]) + self_index


def sign_frontrun_protection_nay_data(block_height):
    return sign_data([nay_prefix, block_height]) + self_index

def pause_deposits(deposit_security_module, self_index):
    deposit_security_module.Pause(self_index, pause_data, {
        'from': account,
        'gas_limit': CONTRACT_GAS_LIMIT, #todo change to less
        'priority_fee': chain.priority_fee*2, #todo increase the max fee as well
    })


def get_deposit_problems(
    account: LocalAccount,
    lido: interface,
    registry: interface,
    eth_chain_id: int,
) -> Tuple[List[str], List[bytes]]:
    """
    Check if all is ready for deposit buffered ether.
    Returns list of problems that prevents deposit.
    """
    deposit_problems = []

    # Check contract status
    if lido.isStopped():
        LIDO_STATUS.state('stopped')
        logger.warning(LIDO_CONTRACT_IS_STOPPED)
        deposit_problems.append(LIDO_CONTRACT_IS_STOPPED)
    else:
        LIDO_STATUS.state('active')

    # Lido contract buffered ether check
    buffered_ether = lido.getBufferedEther()
    BUFFERED_ETHER.set(buffered_ether)
    if buffered_ether < MIN_BUFFERED_ETHER:
        logger.warning(LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)
        deposit_problems.append(LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER)

    # Check that contract has unused operators keys
    if not node_operators_has_free_keys(registry):
        logger.warning(LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS)
        deposit_problems.append(LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS)

    # Account balance check
    if account:
        balance = web3.eth.get_balance(account.address)
        ACCOUNT_BALANCE.set(balance)
        if balance < Wei('0.01 ether'):
            logger.error(NOT_ENOUGH_BALANCE_ON_ACCOUNT)
            deposit_problems.append(NOT_ENOUGH_BALANCE_ON_ACCOUNT)
    else:
        ACCOUNT_BALANCE.set(0)

    # Check gas fee Treshold
    current_gas_fee = chain.base_fee
    GAS_FEE.labels('max_fee').set(MAX_GAS_FEE)
    GAS_FEE.labels('current_fee').set(chain.base_fee)
    if chain.base_fee + chain.priority_fee > MAX_GAS_FEE:
        logger.warning(GAS_FEE_HIGHER_THAN_TRESHOLD)
        deposit_problems.append(GAS_FEE_HIGHER_THAN_TRESHOLD)

    # Check that current gas fee is ok
    recommended_gas_fee = get_recommended_gas_fee()
    if current_gas_fee > recommended_gas_fee:
        logger.warning(GAS_FEE_HIGHER_THAN_RECOMMENDED)
        deposit_problems.append(GAS_FEE_HIGHER_THAN_RECOMMENDED)

    # Get all unused keys that should be deposited next
    keys, signatures = registry.assignNextSigningKeys.call(
        DEPOSIT_AMOUNT,
        {'from': LIDO_CONTRACT_ADDRESSES[eth_chain_id]},
    )

    # Check keys and so on
    signing_keys_set = set()
    for i in range(len(keys)//48):
        signing_keys_list.add(keys[i * 48: (i + 1) * 48])

    used_pub_keys = build_used_pubkeys_map(DEPOSIT_CONTRACT_DEPLOY_BLOCK[web3.eth.chain_id], 
                                web3.eth.block_number, 
                                UNREORGABLE_DISTANCE,
                                EVENT_QUERY_STEP)

    if len(signing_keys_set.intersection(used_pub_keys))>0:
        deposit_problems.append(KEY_WAS_USED)

    return deposit_problems, list(signing_keys_set)


@DEPOSIT_FAILURE.count_exceptions()
def deposit_buffered_ether(account: LocalAccount, lido: interface, signing_keys_list: List[bytes], fp_attest_data):
    lido.depositBufferedEther(len(signing_keys_list), fp_attest_data, {
        'from': account,
        'gas_limit': CONTRACT_GAS_LIMIT,
        'priority_fee': chain.priority_fee,
    })
    SUCCESS_DEPOSIT.inc()


@cache()
def get_recommended_gas_fee() -> float:
    blocks_in_one_day = 6600

    # One week price stats
    gas_fees = get_gas_fee_history()

    # History goes from oldest block to newest
    one_day_fee_hist = gas_fees[- blocks_in_one_day:]
    four_day_fee_hist = gas_fees[- blocks_in_one_day * 3:]

    recommended_price = min(
        numpy.percentile(one_day_fee_hist, GAS_PREDICTION_PERCENTILE),
        numpy.percentile(four_day_fee_hist, GAS_PREDICTION_PERCENTILE),
    )

    GAS_FEE.labels('recommended_fee').set(recommended_price)

    return recommended_price


def get_gas_fee_history():
    last_block = 'latest'
    gas_fees = []

    for i in range(20):
        stats = web3.eth.fee_history(1024, last_block)
        last_block = stats['oldestBlock'] - 2
        gas_fees = stats['baseFeePerGas'] + gas_fees

    return gas_fees


def node_operators_has_free_keys(registry: interface) -> bool:
    """Checking that at least one of the operators has keys"""
    operators_data = [{**registry.getNodeOperator(i, True), **{'index': i}} for i in range(registry.getNodeOperatorsCount())]

    free_keys = 0

    for operator in operators_data:
        free_keys += get_operator_free_keys_count(operator)

    OPERATORS_FREE_KEYS.set(free_keys)

    return bool(free_keys)


def get_operator_free_keys_count(operator: dict) -> int:
    """Check if operator has free keys"""
    free_space = operator['stakingLimit'] - operator['usedSigningKeys']
    keys_to_deposit = operator['totalSigningKeys'] - operator['usedSigningKeys']
    return min(free_space, keys_to_deposit)
