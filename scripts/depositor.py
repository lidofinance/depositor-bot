import time
from typing import Optional

import numpy
from brownie import accounts, chain, interface, web3
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
)
from scripts.depositor_utils.prometheus import (
    GAS_FEE,
    OPERATORS_FREE_KEYS,
    BUFFERED_ETHER,
    CHECK_FAILURE,
    DEPOSIT_FAILURE,
    EXCEPTION_INFO,
    LIDO_STATUS,
    SUCCESS_DEPOSIT, LOG_INFO,
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
        return accounts.load(ACCOUNT_FILENAME)

    if ACCOUNT_PRIVATE_KEY:
        return accounts.add(ACCOUNT_PRIVATE_KEY)

    if accounts:
        return accounts[0]

    # Only for testing propose
    EXCEPTION_INFO.info({'exception': 'Account not provided'})
    return None


def main():
    # Prometheus
    start_http_server(8080)

    account = get_account()

    lido = interface.Lido(LIDO_CONTRACT_ADDRESS, owner=account)
    registry = interface.NodeOperators(OPERATOR_CONTRACT_ADDRESS, owner=account)

    # Just to push keys count to prometheus
    node_operators_has_free_keys(registry)

    while True:
        try:
            pre_deposit_check(lido, registry)
            deposit_buffered_ether(account, lido)
        except (LidoIsStoppedException, NotEnoughBufferedEtherException, NoFreeOperatorKeysException) as error:
            LOG_INFO.info({'exception': str(error)})
            time.sleep(60 * 30)
        except (MaxGasPriceException, RecommendedGasPriceException) as error:
            LOG_INFO.info({'exception': str(error)})
            time.sleep(20)
        except Exception as error:
            EXCEPTION_INFO.info({'exception': str(error)})
            time.sleep(20)


@CHECK_FAILURE.count_exceptions()
def pre_deposit_check(lido: interface, registry: interface):
    """
    Check if everything is ok.
    Throws exception if something is not ok.
    """
    if lido.isStopped():
        LIDO_STATUS.state('stopped')
        msg = '[FAILED] Lido contract is stopped!'
        raise LidoIsStoppedException(msg)
    else:
        LIDO_STATUS.state('active')

    buffered_ether = lido.getBufferedEther()
    BUFFERED_ETHER.set(buffered_ether)
    if buffered_ether < MIN_BUFFERED_ETHER:
        msg = f'[FAILED] Lido has less buffered ether than expected: {buffered_ether}.'
        raise NotEnoughBufferedEtherException(msg)

    current_gas_fee = chain.base_fee
    GAS_FEE.labels('max_fee').set(MAX_GAS_FEE)
    GAS_FEE.labels('current_fee').set(chain.base_fee)

    if chain.base_fee + chain.priority_fee > MAX_GAS_FEE:
        msg = f'[FAILED] base_fee: [{chain.base_fee}] + priority_fee: [{chain.priority_fee}] are too high.'
        raise MaxGasPriceException(msg)

    recommended_gas_fee = get_recommended_gas_fee()
    GAS_FEE.labels('recommended_fee').set(recommended_gas_fee)

    if current_gas_fee > recommended_gas_fee:
        msg = f'[FAILED] Gas fee is too high: [{current_gas_fee}], recommended price: [{recommended_gas_fee}].'
        raise RecommendedGasPriceException(msg)

    if not node_operators_has_free_keys(registry):
        msg = f'[FAILED] No free keys to deposit.'
        raise NoFreeOperatorKeysException(msg)


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
