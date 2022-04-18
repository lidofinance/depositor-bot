import logging
import os

from brownie import Wei, web3, accounts


logger = logging.getLogger(__name__)


NETWORK = os.getenv('NETWORK')

# Transaction limits
MAX_GAS_FEE = Wei(os.getenv('MAX_GAS_FEE', '100 gwei'))
CONTRACT_GAS_LIMIT = Wei(os.getenv('CONTRACT_GAS_LIMIT', 10 * 10**6))

# Gas fee percentile
GAS_FEE_PERCENTILE_1: int = int(os.getenv('GAS_FEE_PERCENTILE_1', 5))
GAS_FEE_PERCENTILE_DAYS_HISTORY_1: int = int(os.getenv('GAS_FEE_PERCENTILE_DAYS_HISTORY_1', 1))

GAS_PRIORITY_FEE_PERCENTILE = int(os.getenv('GAS_PRIORITY_FEE_PERCENTILE', 55))

MIN_PRIORITY_FEE = Wei(os.getenv('MIN_PRIORITY_FEE', '2 gwei'))
MAX_PRIORITY_FEE = Wei(os.getenv('MAX_PRIORITY_FEE', '10 gwei'))

MAX_BUFFERED_ETHERS = Wei(os.getenv('MAX_BUFFERED_ETHERS', '5000 ether'))

# Kafka secrets
KAFKA_BROKER_ADDRESS_1 = os.getenv('KAFKA_BROKER_ADDRESS_1')
KAFKA_USERNAME = os.getenv('KAFKA_USERNAME')
KAFKA_PASSWORD = os.getenv('KAFKA_PASSWORD')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC')
KAFKA_GROUP_PREFIX = os.getenv('KAFKA_GROUP_PREFIX', '')

WEB3_CHAIN_ID = web3.eth.chain_id

# Account private key
WALLET_PRIVATE_KEY = os.getenv('WALLET_PRIVATE_KEY', None)
FLASHBOT_SIGNATURE = os.getenv('FLASHBOT_SIGNATURE')

if WALLET_PRIVATE_KEY:
    ACCOUNT = accounts.add(WALLET_PRIVATE_KEY)
    logger.info({'msg': 'Load account from private key.', 'value': ACCOUNT.address})
else:
    ACCOUNT = None
    logger.warning({'msg': 'Account not provided. Run in dry mode.'})

CREATE_TRANSACTIONS = os.getenv('CREATE_TRANSACTIONS') == 'true'

RAW_WEB3_RPC_ENDPOINTS = os.getenv('WEB3_RPC_ENDPOINTS', '')
WEB3_RPC_ENDPOINTS = RAW_WEB3_RPC_ENDPOINTS.split(',') if RAW_WEB3_RPC_ENDPOINTS else None

PROMETHEUS_PORT = int(os.getenv('PROMETHEUS_PORT', '9000'))
PULSE_SERVER_PORT = int(os.getenv('PULSE_SERVER_PORT', '9010'))

MAX_CYCLE_LIFETIME_IN_SECONDS = int(os.getenv('MAX_CYCLE_LIFETIME_IN_SECONDS', '300'))
