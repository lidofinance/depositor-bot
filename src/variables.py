import logging
import os

from eth_account import Account
from web3 import Web3

logger = logging.getLogger(__name__)


# EL node
WEB3_RPC_ENDPOINTS = os.getenv('WEB3_RPC_ENDPOINTS', '').split(',')

# Account private key
WALLET_PRIVATE_KEY = os.getenv('WALLET_PRIVATE_KEY', None)

if WALLET_PRIVATE_KEY:
    ACCOUNT = Account.from_key(private_key=WALLET_PRIVATE_KEY)
    logger.info({'msg': 'Load account from private key.', 'value': ACCOUNT.address})
else:
    ACCOUNT = None
    logger.warning({'msg': 'Account not provided. Run in dry mode.'})

# App specific
# LIDO_LOCATOR ADDRESS
# Mainnet: 0xC1d0b3DE6792Bf6b4b37EccdcC24e45978Cfd2Eb
# Görli: 0x1eDf09b5023DC86737b59dE68a8130De878984f5
LIDO_LOCATOR = os.getenv('LIDO_LOCATOR', '0xC1d0b3DE6792Bf6b4b37EccdcC24e45978Cfd2Eb')

# DEPOSIT_CONTRACT ADDRESS
# Mainnet: 0x00000000219ab540356cBB839Cbe05303d7705Fa
# Görli: 0xff50ed3d0ec03aC01D4C79aAd74928BFF48a7b2b
DEPOSIT_CONTRACT = os.getenv('DEPOSIT_CONTRACT', '0x00000000219ab540356cBB839Cbe05303d7705Fa')

# rabbit / kafka / rabbit,kafka
MESSAGE_TRANSPORTS = os.getenv('MESSAGE_TRANSPORTS', '').split(',')

# Kafka secrets
KAFKA_BROKER_ADDRESS_1 = os.getenv('KAFKA_BROKER_ADDRESS_1')
KAFKA_USERNAME = os.getenv('KAFKA_USERNAME')
KAFKA_PASSWORD = os.getenv('KAFKA_PASSWORD')
KAFKA_NETWORK = os.getenv('KAFKA_NETWORK', 'mainnet')  # or goerli
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC')
KAFKA_GROUP_PREFIX = os.getenv('KAFKA_GROUP_PREFIX', '')

# rabbit secrets
RABBIT_MQ_URL = os.getenv('RABBIT_MQ_URL', 'ws://127.0.0.1:15674/ws')
RABBIT_MQ_USERNAME = os.getenv('RABBIT_MQ_USERNAME', 'guest')
RABBIT_MQ_PASSWORD = os.getenv('RABBIT_MQ_PASSWORD', 'guest')

# Transactions settings
CREATE_TRANSACTIONS = os.getenv('CREATE_TRANSACTIONS') == 'true'

MIN_PRIORITY_FEE = Web3.toWei(*os.getenv('MIN_PRIORITY_FEE', '50 mwei').split(' '))
MAX_PRIORITY_FEE = Web3.toWei(*os.getenv('MAX_PRIORITY_FEE', '10 gwei').split(' '))

MAX_GAS_FEE = Web3.toWei(*os.getenv('MAX_GAS_FEE', '100 gwei').split(' '))
CONTRACT_GAS_LIMIT = int(os.getenv('CONTRACT_GAS_LIMIT', 15 * 10**6))

# FLASHBOTS_RPC URL
# Mainnet: "https://relay.flashbots.net",
# Görli: "https://relay-goerli.flashbots.net",
FLASHBOTS_RPC = os.getenv('FLASHBOTS_RPC', None)
FLASHBOT_SIGNATURE = os.getenv('FLASHBOT_SIGNATURE', None)

# Curated module strategy
GAS_FEE_PERCENTILE_1: int = int(os.getenv('GAS_FEE_PERCENTILE_1', 20))
GAS_FEE_PERCENTILE_DAYS_HISTORY_1: int = int(os.getenv('GAS_FEE_PERCENTILE_DAYS_HISTORY_1', 1))

GAS_PRIORITY_FEE_PERCENTILE = int(os.getenv('GAS_PRIORITY_FEE_PERCENTILE', 25))

MAX_BUFFERED_ETHERS = Web3.toWei(*os.getenv('MAX_BUFFERED_ETHERS', '5000 ether').split(' '))

# Metrics
PROMETHEUS_PORT = int(os.getenv('PROMETHEUS_PORT', '9000'))
PULSE_SERVER_PORT = int(os.getenv('PULSE_SERVER_PORT', '9010'))
MAX_CYCLE_LIFETIME_IN_SECONDS = int(os.getenv('MAX_CYCLE_LIFETIME_IN_SECONDS', '1200'))

# List of ids of staking modules in which the depositor bot will make deposits
DEPOSIT_MODULES_WHITELIST = [int(module_id) for module_id in os.getenv('DEPOSIT_MODULES_WHITELIST', '1').split(',')]
