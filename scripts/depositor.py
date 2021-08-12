import logging
import os
import time

from brownie import accounts, chain, web3, interface
from brownie.network.account import LocalAccount


# Sub-units of Ether
ETHER = 10**18
GWEI = 10**9
MWEI = 10**6

# Transaction limits
MAX_GAS_PRICE = 100 * GWEI
CONTRACT_GAS_LIMIT = 10 * MWEI

# Hardcoded prices
DEPOSIT_AMOUNT = 150
MIN_BUFFERED_ETHER = 32 * 8 * ETHER

# LIDO
LIDO_CONTRACT_ADDRESS = '0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84'


def main():
    """Transfer tokens from account to LIDO contract while gas price is low"""
    account_filename = os.getenv('ACCOUNT_FILENAME', None)
    if account_filename is None:
        logging.error(str('ACCOUNT_FILENAME env should be provided'))
        return

    account = get_account(account_filename)
    contract = get_lido_contract(LIDO_CONTRACT_ADDRESS, account)

    # Transfer money
    deposit_to_contract(contract, account)


def get_account(account_filename: str) -> LocalAccount:
    return accounts.load(account_filename)


def get_lido_contract(contract_address: str, owner: LocalAccount) -> interface:
    return interface.Lido(contract_address, owner=owner)


def deposit_to_contract(lido: interface, account: LocalAccount):
    for _ in chain.new_blocks():
        current_gas_price = web3.eth.generate_gas_price()
        if current_gas_price > MAX_GAS_PRICE:
            continue

        if lido.isStopped():
            continue

        if lido.getBufferedEther() < MIN_BUFFERED_ETHER:
            continue

        try:
            lido.depositBufferedEther(DEPOSIT_AMOUNT, {
                'gas_price': current_gas_price,
                'from': account,
                'gas_limit': CONTRACT_GAS_LIMIT,
            })
        except Exception as exception:
            logging.error(str(exception))

        time.sleep(120)
