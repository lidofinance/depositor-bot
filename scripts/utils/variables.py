import logging
import os

from brownie import Wei, web3, accounts

logger = logging.getLogger(__name__)


NETWORK = os.getenv('NETWORK')

# Account private key
WALLET_PRIVATE_KEY = os.getenv('WALLET_PRIVATE_KEY', None)

# Transaction limits
MAX_GAS_FEE = Wei(os.getenv('MAX_GAS_FEE', '100 gwei'))
CONTRACT_GAS_LIMIT = Wei(os.getenv('CONTRACT_GAS_LIMIT', 10 * 10**6))
MIN_BUFFERED_ETHER = Wei(os.getenv('MIN_BUFFERED_ETHER', '1024 ether'))

# Gas fee percentile
GAS_FEE_PERCENTILE = int(os.getenv('GAS_FEE_PERCENTILE', 30))
GAS_FEE_PERCENTILE_DAYS_HISTORY = int(os.getenv('GAS_FEE_PERCENTILE_DAYS_HISTORY', 2))
GAS_PRIORITY_FEE_PERCENTILE = int(os.getenv('GAS_PRIORITY_FEE_PERCENTILE', 55))

# Kafka secrets
KAFKA_BROKER_ADDRESS_1 = os.getenv('KAFKA_BROKER_ADDRESS_1')
KAFKA_USERNAME = os.getenv('KAFKA_USERNAME')
KAFKA_PASSWORD = os.getenv('KAFKA_PASSWORD')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC')

WEB3_CHAIN_ID = web3.eth.chain_id

if WALLET_PRIVATE_KEY:
    ACCOUNT = accounts.add(WALLET_PRIVATE_KEY)
    logger.info({'msg': 'Load account from private key.', 'value': ACCOUNT.address})
else:
    ACCOUNT = None
    logger.warning({'msg': 'Account not provided. Run in dry mode.'})

CREATE_TRANSACTIONS = os.getenv('CREATE_TRANSACTIONS') == 'true'
