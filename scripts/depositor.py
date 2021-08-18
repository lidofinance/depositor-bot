import logging
import os

from brownie import accounts, chain, interface, Wei
from brownie.network.account import LocalAccount

from strategy.gas_strategy import get_scaling_in_time_gas_strategy


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
MAX_WAITING_TIME = os.getenv('MAX_WAITING_TIME', 25 * 60 * 60)  # One day in seconds
MAX_GAS_PRICE = os.getenv('MAX_GAS_PRICE', Wei('100 gwei'))
CONTRACT_GAS_LIMIT = os.getenv('CONTRACT_GAS_LIMIT', Wei('10 mwei'))

# Contract related vars
DEPOSIT_AMOUNT = os.getenv('DEPOSIT_AMOUNT', 150)
MIN_BUFFERED_ETHER = Wei('256 ether')
LIDO_CONTRACT_ADDRESS = '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84'


class ConfigurationException(Exception):
    pass


def main():
    """Transfer tokens from account to LIDO contract while gas price is low"""
    logging.info('Start daemon.')

    account = get_account()
    contract = get_lido_contract(account)

    # Transfer money
    deposit_to_contract(contract, account)


def get_account() -> LocalAccount:
    if ACCOUNT_PRIVATE_KEY:
        logging.info(str('Load account from private key.'))
        return accounts.add(ACCOUNT_PRIVATE_KEY)

    if accounts:
        logging.info(str('Test mode is on. Took the first account.'))
        return accounts[0]

    logging.error('No account found fot selected network. Provide ACCOUNT_FILENAME env.')
    raise ConfigurationException('Account was not found. Provide ACCOUNT_FILENAME and ACCOUNT_PASSWORD env.')


def get_lido_contract(owner: LocalAccount) -> interface:
    logging.info(f'Load contract interface.')
    return interface.Lido(LIDO_CONTRACT_ADDRESS, owner=owner)


def deposit_to_contract(lido: interface, account: LocalAccount):
    logging.info(f'Start depositing.')

    for _ in chain.new_blocks():
        logging.info(f'New deposit cycle.')
        if lido.isStopped():
            logging.error(f'Lido contract is stopped!')
            break

        buffered_ether = lido.getBufferedEther()
        if buffered_ether < MIN_BUFFERED_ETHER:
            logging.warning(f'Lido has less buffered ether than expected: {buffered_ether}.')
            continue

        gas_strategy = get_scaling_in_time_gas_strategy(
            max_waiting_time=MAX_WAITING_TIME,
            max_gas_price=MAX_GAS_PRICE,
        )

        try:
            logging.info(f'Trying to deposit with Scaling In Time Gas Strategy.')
            lido.depositBufferedEther(DEPOSIT_AMOUNT, {
                'gas_price': gas_strategy,
                'from': account,
                'gas_limit': CONTRACT_GAS_LIMIT,
            })
        except Exception as exception:
            logging.error(str(exception))
