import logging
import os
from typing import Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import URI
from web3 import Web3

logger = logging.getLogger(__name__)

# EL node
WEB3_RPC_ENDPOINTS = os.getenv('WEB3_RPC_ENDPOINTS', '').split(',')

TESTNET_WEB3_RPC_ENDPOINTS = os.getenv('TESTNET_WEB3_RPC_ENDPOINTS', '').split(',')

# Account private key
WALLET_PRIVATE_KEY = os.getenv('WALLET_PRIVATE_KEY', None)

ACCOUNT: Optional[LocalAccount]
if WALLET_PRIVATE_KEY:
    ACCOUNT = Account.from_key(WALLET_PRIVATE_KEY)
    logger.info({'msg': 'Load account from private key.', 'value': ACCOUNT.address})
else:
    ACCOUNT = None
    logger.warning({'msg': 'Account not provided. Run in dry mode.'})

# App specific
# LIDO_LOCATOR ADDRESS
# Mainnet: 0xC1d0b3DE6792Bf6b4b37EccdcC24e45978Cfd2Eb
# Holesky: 0x28FAB2059C713A7F9D8c86Db49f9bb0e96Af1ef8
LIDO_LOCATOR = Web3.to_checksum_address(os.getenv('LIDO_LOCATOR', '0xC1d0b3DE6792Bf6b4b37EccdcC24e45978Cfd2Eb'))

# DEPOSIT_CONTRACT ADDRESS
# Mainnet: 0x00000000219ab540356cBB839Cbe05303d7705Fa
# Holesky: 0x4242424242424242424242424242424242424242
DEPOSIT_CONTRACT = Web3.to_checksum_address(os.getenv('DEPOSIT_CONTRACT', '0x00000000219ab540356cBB839Cbe05303d7705Fa'))

# rabbit / onchain_transport
MESSAGE_TRANSPORTS = os.getenv('MESSAGE_TRANSPORTS', '').split(',')

# rabbit secrets
RABBIT_MQ_URL = os.getenv('RABBIT_MQ_URL', 'ws://127.0.0.1:15674/ws')
RABBIT_MQ_USERNAME = os.getenv('RABBIT_MQ_USERNAME', 'guest')
RABBIT_MQ_PASSWORD = os.getenv('RABBIT_MQ_PASSWORD', 'guest')

# data bus
# gnosis nodes
ONCHAIN_TRANSPORT_RPC_ENDPOINTS = os.getenv('ONCHAIN_TRANSPORT_RPC_ENDPOINTS', '').split(',')

ONCHAIN_TRANSPORT_ADDRESS = os.getenv('ONCHAIN_TRANSPORT_ADDRESS', None)
if ONCHAIN_TRANSPORT_ADDRESS:
    # bot will throw exception if there is unexpected str and it's ok
    # Expecting onchain databus contract address
    ONCHAIN_TRANSPORT_ADDRESS = Web3.to_checksum_address(ONCHAIN_TRANSPORT_ADDRESS)

# Transactions settings
CREATE_TRANSACTIONS = os.getenv('CREATE_TRANSACTIONS') == 'true'

MIN_PRIORITY_FEE = Web3.to_wei(*os.getenv('MIN_PRIORITY_FEE', '50 mwei').split(' '))
MAX_PRIORITY_FEE = Web3.to_wei(*os.getenv('MAX_PRIORITY_FEE', '10 gwei').split(' '))

MAX_GAS_FEE = Web3.to_wei(*os.getenv('MAX_GAS_FEE', '100 gwei').split(' '))
CONTRACT_GAS_LIMIT = int(os.getenv('CONTRACT_GAS_LIMIT', 15 * 10**6))

# Mainnet: "https://relay.flashbots.net",
# Holesky: "https://relay-holesky.flashbots.net",
RELAY_RPC = URI(os.getenv('RELAY_RPC', os.getenv('FLASHBOTS_RPC', '')))
AUCTION_BUNDLER_PRIVATE_KEY = os.getenv('AUCTION_BUNDLER_PRIVATE_KEY', os.getenv('FLASHBOT_SIGNATURE', ''))

# Curated module strategy
GAS_FEE_PERCENTILE_1: int = int(os.getenv('GAS_FEE_PERCENTILE_1', 20))
GAS_FEE_PERCENTILE_DAYS_HISTORY_1: int = int(os.getenv('GAS_FEE_PERCENTILE_DAYS_HISTORY_1', 1))

GAS_PRIORITY_FEE_PERCENTILE = int(os.getenv('GAS_PRIORITY_FEE_PERCENTILE', 25))

MAX_BUFFERED_ETHERS = Web3.to_wei(*os.getenv('MAX_BUFFERED_ETHERS', '5000 ether').split(' '))

# Metrics
PROMETHEUS_PORT = int(os.getenv('PROMETHEUS_PORT', '9000'))
PROMETHEUS_PREFIX = os.getenv('PROMETHEUS_PREFIX', 'depositor_bot')
HEALTHCHECK_SERVER_PORT = int(os.getenv('HEALTHCHECK_SERVER_PORT', os.getenv('PULSE_SERVER_PORT', '9010')))
MAX_CYCLE_LIFETIME_IN_SECONDS = int(os.getenv('MAX_CYCLE_LIFETIME_IN_SECONDS', '1200'))

# List of ids of staking modules in which the depositor bot will make deposits
_env_whitelist = os.getenv('DEPOSIT_MODULES_WHITELIST', '').strip()
DEPOSIT_MODULES_WHITELIST = [int(module_id) for module_id in _env_whitelist.split(',')] if _env_whitelist else []

"""
GAS_ADDENDUM is used to increase number of deposits during to calm market. The value should be increased if bot
wants to deposit more often.
The value 6 was calculated this way:
profit_per_val = 32 * 10**9 * 0.03(APR) / 12 / 30
gas_per_validator = 112176
x = profit_per_val / gas_per_validator

x / 4(we assume that chances of significant gas drop during 8 hours are low)
"""
GAS_ADDENDUM = Web3.to_wei(*os.getenv('GAS_ADDENDUM', '6 gwei').split(' '))

# All non-private env variables to the logs in main
PUBLIC_ENV_VARS = {
    'LIDO_LOCATOR': LIDO_LOCATOR,
    'DEPOSIT_CONTRACT': DEPOSIT_CONTRACT,
    'MESSAGE_TRANSPORTS': MESSAGE_TRANSPORTS,
    'CREATE_TRANSACTIONS': CREATE_TRANSACTIONS,
    'MIN_PRIORITY_FEE': MIN_PRIORITY_FEE,
    'MAX_PRIORITY_FEE': MAX_PRIORITY_FEE,
    'MAX_GAS_FEE': MAX_GAS_FEE,
    'RELAY_RPC': RELAY_RPC,
    'GAS_FEE_PERCENTILE_1': GAS_FEE_PERCENTILE_1,
    'GAS_FEE_PERCENTILE_DAYS_HISTORY_1': GAS_FEE_PERCENTILE_DAYS_HISTORY_1,
    'GAS_PRIORITY_FEE_PERCENTILE': GAS_PRIORITY_FEE_PERCENTILE,
    'MAX_BUFFERED_ETHERS': MAX_BUFFERED_ETHERS,
    'PROMETHEUS_PORT': PROMETHEUS_PORT,
    'PROMETHEUS_PREFIX': PROMETHEUS_PREFIX,
    'HEALTHCHECK_SERVER_PORT': HEALTHCHECK_SERVER_PORT,
    'MAX_CYCLE_LIFETIME_IN_SECONDS': MAX_CYCLE_LIFETIME_IN_SECONDS,
    'DEPOSIT_MODULES_WHITELIST': DEPOSIT_MODULES_WHITELIST,
    'ACCOUNT': '' if ACCOUNT is None else ACCOUNT.address,
    'ONCHAIN_TRANSPORT_ADDRESS': ONCHAIN_TRANSPORT_ADDRESS,
}

PRIVATE_ENV_VARS = {
    'WEB3_RPC_ENDPOINTS': WEB3_RPC_ENDPOINTS,
    'ONCHAIN_TRANSPORT_RPC_ENDPOINTS': ONCHAIN_TRANSPORT_RPC_ENDPOINTS,
    'WALLET_PRIVATE_KEY': WALLET_PRIVATE_KEY,
    'RABBIT_MQ_URL': RABBIT_MQ_URL,
    'RABBIT_MQ_USERNAME': RABBIT_MQ_USERNAME,
    'RABBIT_MQ_PASSWORD': RABBIT_MQ_PASSWORD,
    'AUCTION_BUNDLER_PRIVATE_KEY': AUCTION_BUNDLER_PRIVATE_KEY,
}

assert not set(PRIVATE_ENV_VARS.keys()).intersection(set(PUBLIC_ENV_VARS.keys()))
