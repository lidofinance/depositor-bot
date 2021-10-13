import os

from brownie import Wei


# Account private key
ACCOUNT_FILENAME = os.getenv('ACCOUNT_FILENAME', None)
ACCOUNT_PRIVATE_KEY = os.getenv('ACCOUNT_PRIVATE_KEY', None)

# Transaction limits
MAX_GAS_FEE = Wei(os.getenv('MAX_GAS_FEE', '250 gwei'))
CONTRACT_GAS_LIMIT = Wei(os.getenv('CONTRACT_GAS_LIMIT', 10 * 10**6))

# Contract related vars
# 155 Keys is the optimal value
MIN_BUFFERED_ETHER = Wei(os.getenv('MIN_BUFFERED_ETHER', '1024 ether'))
