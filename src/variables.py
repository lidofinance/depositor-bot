import logging
import os

from eth_account import Account
from web3 import Web3

from blockchain.constants import NETWORK_CHAIN_ID, Network
from variables_types import TransportType

logger = logging.getLogger(__name__)


NETWORK = os.getenv('NETWORK')
ENVIRONMENT = os.getenv('ENVIRONMENT', '')

# Transaction limits
MAX_GAS_FEE = Web3.toWei(*os.getenv('MAX_GAS_FEE', '100 gwei').split(' '))
CONTRACT_GAS_LIMIT = int(os.getenv('CONTRACT_GAS_LIMIT', 15 * 10**6))

# Gas fee percentile
GAS_FEE_PERCENTILE_1: int = int(os.getenv('GAS_FEE_PERCENTILE_1', 5))
GAS_FEE_PERCENTILE_DAYS_HISTORY_1: int = int(os.getenv('GAS_FEE_PERCENTILE_DAYS_HISTORY_1', 1))

GAS_PRIORITY_FEE_PERCENTILE = int(os.getenv('GAS_PRIORITY_FEE_PERCENTILE', 25))

MIN_PRIORITY_FEE = Web3.toWei(*os.getenv('MIN_PRIORITY_FEE', '1 gwei').split(' '))
MAX_PRIORITY_FEE = Web3.toWei(*os.getenv('MAX_PRIORITY_FEE', '10 gwei').split(' '))

MAX_BUFFERED_ETHERS = Web3.toWei(*os.getenv('MAX_BUFFERED_ETHERS', '5000 ether').split(' '))

# Kafka secrets
KAFKA_BROKER_ADDRESS_1 = os.getenv('KAFKA_BROKER_ADDRESS_1')
KAFKA_USERNAME = os.getenv('KAFKA_USERNAME')
KAFKA_PASSWORD = os.getenv('KAFKA_PASSWORD')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC')
KAFKA_GROUP_PREFIX = os.getenv('KAFKA_GROUP_PREFIX', '')

# Should be reinitialized after brownie pre-script
WEB3_CHAIN_ID = NETWORK_CHAIN_ID.get(NETWORK, Network.Mainnet)

# Account private key
WALLET_PRIVATE_KEY = os.getenv('WALLET_PRIVATE_KEY', None)
FLASHBOT_SIGNATURE = os.getenv('FLASHBOT_SIGNATURE', None)

if WALLET_PRIVATE_KEY:
    ACCOUNT = Account.from_key(WALLET_PRIVATE_KEY)
    logger.info({'msg': 'Load account from private key.', 'value': ACCOUNT.address})
else:
    ACCOUNT = None
    logger.warning({'msg': 'Account not provided. Run in dry mode.'})

CREATE_TRANSACTIONS = os.getenv('CREATE_TRANSACTIONS') == 'true'

WEB3_RPC_ENDPOINTS = os.getenv('WEB3_RPC_ENDPOINTS', '').split(',')

PROMETHEUS_PORT = int(os.getenv('PROMETHEUS_PORT', '9000'))
PULSE_SERVER_PORT = int(os.getenv('PULSE_SERVER_PORT', '9010'))

MAX_CYCLE_LIFETIME_IN_SECONDS = int(os.getenv('MAX_CYCLE_LIFETIME_IN_SECONDS', '30000'))

RABBIT_MQ_URL = os.getenv('RABBIT_MQ_URL', 'ws://127.0.0.1:15674/ws')

RABBIT_MQ_USERNAME = os.getenv('RABBIT_MQ_USERNAME', 'guest')
RABBIT_MQ_PASSWORD = os.getenv('RABBIT_MQ_PASSWORD', 'guest')

# rabbit / kafka or rabbit,kafka
MESSAGE_TRANSPORTS = os.getenv('MESSAGE_TRANSPORTS', TransportType.RABBIT).split(',')
