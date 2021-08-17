import logging
import os

from brownie import accounts, chain, web3, interface
from brownie.network.account import LocalAccount


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)


# Sub-units of Ether
ETHER = 10**18
GWEI = 10**9
MWEI = 10**6

# Transaction limits
MAX_GAS_PRICE = os.getenv('MAX_GAS_PRICE', 100 * GWEI)
CONTRACT_GAS_LIMIT = os.getenv('CONTRACT_GAS_LIMIT', 10 * MWEI)

# Hardcoded prices
DEPOSIT_AMOUNT = os.getenv('DEPOSIT_AMOUNT', 150)
MIN_BUFFERED_ETHER = 32 * 8 * ETHER

# LIDODWQD SAD
LIDO_CONTRACT_ADDRESS = '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84'

ACCOUNT_FILENAME = os.getenv('ACCOUNT_FILENAME', None)
ACCOUNT_PASSWORD = os.getenv('ACCOUNT_PASSWORD', None)


class ConfigException(Exception):
    pass


def main():
    """Transfer tokens from account to LIDO contract while gas price is low"""
    logging.info('Start daemon.')
    account = get_account()
    contract = get_lido_contract(account)

    # Transfer money
    deposit_to_contract(contract, account)


def get_account() -> LocalAccount:
    if ACCOUNT_FILENAME:
        logging.info(str('Loading account from file.'))
        return accounts.load(ACCOUNT_FILENAME, ACCOUNT_PASSWORD)

    if accounts:
        logging.info(str('Test mode is on. Took the first account.'))
        return accounts[0]

    logging.error('No account found fot selected network. Provide ACCOUNT_FILENAME env.')
    raise ConfigException('Account was not found. Provide ACCOUNT_FILENAME and ACCOUNT_PASSWORD env.')


def get_lido_contract(owner: LocalAccount) -> interface:
    return interface.Lido(LIDO_CONTRACT_ADDRESS, owner=owner)


def deposit_to_contract(lido: interface, account: LocalAccount):
    logging.info(f'Start depositing.')
    for _ in chain.new_blocks():
        current_gas_price = web3.eth.generate_gas_price()
        if current_gas_price > MAX_GAS_PRICE:
            logging.warning(f'Gas price is too high: {current_gas_price}.')
            continue

        if lido.isStopped():
            logging.error(f'Lido contract is stopped!')
            break

        buffered_ether = lido.getBufferedEther()
        if buffered_ether < MIN_BUFFERED_ETHER:
            logging.warning(f'Lido has less buffered ether than expected: {buffered_ether}.')
            continue

        try:
            logging.info(f'Deposit buffered ether {DEPOSIT_AMOUNT} with gas price: {current_gas_price}.')
            lido.depositBufferedEther(DEPOSIT_AMOUNT, {
                'gas_price': current_gas_price,
                'from': account,
                'gas_limit': CONTRACT_GAS_LIMIT,
            })
        except Exception as exception:
            logging.error(str(exception))

        # time.sleep(120)
