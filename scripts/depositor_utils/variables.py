import os

from brownie import Wei


NETWORK = os.getenv('NETWORK')

# Account private key
ACCOUNT_FILENAME = os.getenv('ACCOUNT_FILENAME', None)
ACCOUNT_PRIVATE_KEY = os.getenv('ACCOUNT_PRIVATE_KEY', None)

# Transaction limits
MAX_GAS_FEE = Wei(os.getenv('MAX_GAS_FEE', '100 gwei'))
CONTRACT_GAS_LIMIT = Wei(os.getenv('CONTRACT_GAS_LIMIT', 10 * 10**6))

# Kafka secrets
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS')
KAFKA_SASL_USERNAME = os.getenv('KAFKA_SASL_USERNAME')
KAFKA_SASL_PASSWORD = os.getenv('KAFKA_SASL_PASSWORD')
KAFKA_TOPIC_NAME = os.getenv('KAFKA_TOPIC_NAME')
