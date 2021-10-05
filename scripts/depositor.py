import time
from typing import Optional

import numpy
from brownie import accounts, chain, interface, web3, Wei
from brownie.network.account import LocalAccount
from prometheus_client.exposition import start_http_server

from scripts.depositor_utils.constants import (
    LIDO_CONTRACT_ADDRESS,
    OPERATOR_CONTRACT_ADDRESS,
)
from scripts.depositor_utils.exceptions import (
    LidoIsStoppedException,
    NotEnoughBufferedEtherException,
    NoFreeOperatorKeysException,
    MaxGasPriceException,
    RecommendedGasPriceException,
    NotEnoughBalance,
)
from scripts.depositor_utils.loki import logger
from scripts.depositor_utils.prometheus import (
    GAS_FEE,
    OPERATORS_FREE_KEYS,
    BUFFERED_ETHER,
    CHECK_FAILURE,
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
        try:
            logger.info('Do deposit pre-checks.')
            pre_deposit_check(account, lido, registry)
            logger.info('Do deposit.')
            deposit_buffered_ether(account, lido)
        except (LidoIsStoppedException, NotEnoughBufferedEtherException, NoFreeOperatorKeysException, NotEnoughBalance):
            time.sleep(60 * 30)
        except (MaxGasPriceException, RecommendedGasPriceException):
            time.sleep(20)
        except Exception as error:
            logger.error(str(error))
            time.sleep(20)


@CHECK_FAILURE.count_exceptions()
def pre_deposit_check(account: LocalAccount, lido: interface, registry: interface):
    """
    Check if everything is ok.
    Throws exception if something is not ok.
    """
    # Lido contract status check
    if lido.isStopped():
        LIDO_STATUS.state('stopped')
        msg = 'Lido contract is stopped!'
        logger.warning(msg)
        raise LidoIsStoppedException(msg)
    else:
        LIDO_STATUS.state('active')

    # Account balance check
    balance = web3.eth.get_balance(account.address)
    ACCOUNT_BALANCE.set(balance)
    if balance < Wei('0.01 ether'):
        msg = f'Account balance is too low'
        logger.warning(msg)
        raise NotEnoughBalance(msg)

    # Lido contract buffered ether
    buffered_ether = lido.getBufferedEther()
    BUFFERED_ETHER.set(buffered_ether)
    if buffered_ether < MIN_BUFFERED_ETHER:
        msg = f'Lido has less buffered ether than expected: {buffered_ether}.'
        logger.warning(msg)
        raise NotEnoughBufferedEtherException(msg)

    # Check that contract has unused operators keys
    if not node_operators_has_free_keys(registry):
        msg = f'No free keys to deposit.'
        logger.warning(msg)
        raise NoFreeOperatorKeysException(msg)

    # We cant spent more than MAX_GAS_FEE
    current_gas_fee = chain.base_fee
    GAS_FEE.labels('max_fee').set(MAX_GAS_FEE)
    GAS_FEE.labels('current_fee').set(chain.base_fee)
    if chain.base_fee + chain.priority_fee > MAX_GAS_FEE:
        msg = f'base_fee: [{chain.base_fee}] + priority_fee: [{chain.priority_fee}] are too high.'
        logger.warning(msg)
        raise MaxGasPriceException(msg)

    # Check that current gas fee is ok
    recommended_gas_fee = get_recommended_gas_fee()
    GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)
    if current_gas_fee > recommended_gas_fee:
        msg = f'Gas fee is too high: [{current_gas_fee}], recommended price: [{recommended_gas_fee}].'
        logger.warning(msg)
        raise RecommendedGasPriceException(msg)


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
    four_day_fee_hist = gas_fees[- blocks_in_one_day * 4:]

    recommended_price = min(
        numpy.percentile(one_day_fee_hist, GAS_PREDICTION_PERCENTILE),
        numpy.percentile(four_day_fee_hist, GAS_PREDICTION_PERCENTILE),
    )

    return recommended_price


def get_gas_fee_history():
    last_block = 'latest'
    gas_fees = []

    for i in range(26):
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
