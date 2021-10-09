import time
from typing import Optional, List

import numpy
from brownie import accounts, chain, interface, web3, Wei
from brownie.network.account import LocalAccount
from prometheus_client.exposition import start_http_server

from scripts.depositor_utils.constants import (
    LIDO_CONTRACT_ADDRESS,
    OPERATOR_CONTRACT_ADDRESS,
)
from scripts.depositor_utils.deposit_problems import (
    LIDO_CONTRACT_IS_STOPPED,
    NOT_ENOUGH_BALANCE_ON_ACCOUNT,
    LIDO_CONTRACT_HAS_NOT_ENOUGH_BUFFERED_ETHER,
    LIDO_CONTRACT_HAS_NOT_ENOUGH_SUBMITTED_KEYS,
    GAS_FEE_HIGHER_THAN_TRESHOLD,
    GAS_FEE_HIGHER_THAN_RECOMMENDED
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
from scripts.depositor_utils.variables import (
    MIN_BUFFERED_ETHER,
    MAX_GAS_FEE,
    ACCOUNT_FILENAME,
    ACCOUNT_PRIVATE_KEY,
    DEPOSIT_AMOUNT,
    CONTRACT_GAS_LIMIT,
    GAS_PREDICTION_PERCENTILE,
)
from scripts.depositor_utils.utils import cache


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

    lido = interface.Lido(LIDO_CONTRACT_ADDRESS, owner=account)
    registry = interface.NodeOperators(OPERATOR_CONTRACT_ADDRESS, owner=account)

    while True:
        logger.info('New deposit cycle.')
        problems = get_deposit_problems(account, lido, registry)
        if not problems:
            try:
                logger.info(f'Try to deposit.')
                deposit_buffered_ether(account, lido)
            except Exception as error:
                logger.error(str(error))
                time.sleep(15)
        else:
            logger.info(f'Deposit cancelled. Problems count: {len(problems)}')
            time.sleep(15)


def get_deposit_problems(account: LocalAccount, lido: interface, registry: interface) -> List[str]:
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

    return deposit_problems


@DEPOSIT_FAILURE.count_exceptions()
def deposit_buffered_ether(account: LocalAccount, lido: interface):
    lido.depositBufferedEther(DEPOSIT_AMOUNT, {
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
