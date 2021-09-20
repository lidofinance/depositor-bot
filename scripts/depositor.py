import logging
import os
import time

import numpy
from brownie import accounts, chain, interface, Wei, web3
from brownie.network.account import LocalAccount
from web3.exceptions import BlockNotFound

from scripts.utils import cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)


ACCOUNT_PRIVATE_KEY = os.getenv('ACCOUNT_PRIVATE_KEY', None)

# Transaction limits
MAX_GAS_PRICE = Wei(os.getenv('MAX_GAS_PRICE', '100 gwei'))
CONTRACT_GAS_LIMIT = Wei(os.getenv('CONTRACT_GAS_LIMIT', 10 ** 10 * 6))

# Contract related vars
# 155 Keys is the optimal value
DEPOSIT_AMOUNT = os.getenv('DEPOSIT_AMOUNT', 155)
MIN_BUFFERED_ETHER = Wei('256 ether')
LIDO_CONTRACT_ADDRESS = '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84'
OPERATOR_CONTRACT_ADDRESS = '0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5'

# GAS STRATEGY SETTINGS
GAS_PREDICTION_PERCENTILE = os.getenv('GAS_PREDICTION_PERCENTILE', 20)


class ConfigurationException(Exception):
    pass


def main():
    """Transfer tokens from account to LIDO contract while gas price is low"""
    logging.info('Start daemon.')

    account = get_account()
    lido = get_lido_contract(account)
    registry = get_operator_contract(account)

    # Transfer money
    while True:
        try:
            deposit_to_contract(lido, registry, account)
        except BlockNotFound:
            logging.warning('BlockNotFound exception raised.')
            time.sleep(20)


def get_account() -> LocalAccount:
    if ACCOUNT_PRIVATE_KEY:
        logging.info(str('Load account from private key.'))
        return accounts.add(ACCOUNT_PRIVATE_KEY)

    if accounts:
        logging.info('[Test] Test mode is on. Took the first account.')
        return accounts[0]

    logging.warning('[Test] Running in test mode without account.')


def get_lido_contract(owner: LocalAccount) -> interface:
    logging.info(f'Load Lido contract interface.')
    return interface.Lido(LIDO_CONTRACT_ADDRESS, owner=owner)


def get_operator_contract(owner: LocalAccount) -> interface:
    logging.info(f'Load Operator contract interface.')
    return interface.NodeOperators(OPERATOR_CONTRACT_ADDRESS, owner=owner)


@cache()
def get_recommended_gas_fee() -> float:
    logging.info('Fetch gas fee history.')
    # One week price stats
    last_block = 'latest'
    gas_prices = []

    # Fetch four day history
    for i in range(24):
        stats = web3.eth.fee_history(1024, last_block)
        last_block = stats['oldestBlock'] - 2
        gas_prices.extend(stats['baseFeePerGas'])

    one_day_hist = gas_prices[:6600]
    four_day_hist = gas_prices[:24576]

    recommended_price = min(
        numpy.percentile(one_day_hist, GAS_PREDICTION_PERCENTILE),
        numpy.percentile(four_day_hist, GAS_PREDICTION_PERCENTILE),
    )

    logging.info(f'Recommended gas price: [{recommended_price}]')

    return recommended_price


def free_keys_to_deposit_exists(registry) -> bool:
    operators_data = [{**registry.getNodeOperator(i, True), **{'index': i}} for i in range(registry.getNodeOperatorsCount())]

    for operator in operators_data:
        if operator_has_free_keys(operator):
            return True

    return False


def operator_has_free_keys(operator) -> bool:
    free_space = operator['stakingLimit'] - operator['usedSigningKeys']
    keys_to_deposit = operator['totalSigningKeys'] - operator['usedSigningKeys']

    return free_space and keys_to_deposit


def deposit_to_contract(lido: interface, registry: interface, account: LocalAccount):
    logging.info(f'Start depositing.')

    for _ in chain.new_blocks():
        logging.info(f'New deposit cycle.')
        if lido.isStopped():
            logging.warning(f'[FAILED] Lido contract is stopped!')
            time.sleep(120)
            continue

        buffered_ether = lido.getBufferedEther()
        if buffered_ether < MIN_BUFFERED_ETHER:
            logging.warning(f'[FAILED] Lido has less buffered ether than expected: {buffered_ether}.')
            continue

        if chain.base_fee + chain.priority_fee > MAX_GAS_PRICE:
            logging.warning(f'[FAILED] base_fee: [{chain.base_fee}] + priority_fee: [{chain.priority_fee}] are too high.')
            time.sleep(60)
            continue

        recommended_gas_price = get_recommended_gas_fee()
        if chain.base_fee > recommended_gas_price:
            logging.warning(f'[FAILED] Gas fee is to high: [{chain.base_fee}], recommended price: [{recommended_gas_price}].')
            continue

        if not free_keys_to_deposit_exists(registry):
            logging.info(f'[FAILED] No free keys to deposit.')
            time.sleep(600)
            continue

        try:
            if account:
                logging.info(f'[SUCCESS] Trying to deposit using EIP-1559.')
                lido.depositBufferedEther(DEPOSIT_AMOUNT, {
                    'from': account,
                    'gas_limit': CONTRACT_GAS_LIMIT,
                    'priority_fee': chain.priority_fee,
                })
            else:
                logging.info(f'[SUCCESS] [Test] Deposit buffered ether call with gas price [{chain.base_fee}].')
        except Exception as exception:
            logging.error(str(exception))
            time.sleep(120)
