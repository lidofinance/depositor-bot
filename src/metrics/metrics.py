from prometheus_client.metrics import Gauge, Counter, Histogram

PREFIX = 'depositor_bot'

BUILD_INFO = Gauge('build_info', 'Build info', [
    'name',
    'network',
    'max_gas_fee',
    'max_buffered_ethers',
    'contract_gas_limit',
    'gas_fee_percentile_1',
    'gas_fee_percentile_days_history_1',
    'gas_priority_fee_percentile',
    'min_priority_fee',
    'max_priority_fee',
    'kafka_topic',
    'account_address',
    'create_transactions',
], namespace=PREFIX)

GAS_FEE = Gauge('gas_fee', 'Gas fee', ['type', 'module_id'], namespace=PREFIX)

TX_SEND = Counter('transactions_send', 'Amount of send transaction from bot.', ['status'], namespace=PREFIX)

ACCOUNT_BALANCE = Gauge('account_balance', 'Account balance', namespace=PREFIX)

DEPOSIT_MESSAGES = Gauge(
    'deposit_messages',
    'Guardians deposit messages',
    ['address', 'version'],
    namespace=PREFIX,
)
PAUSE_MESSAGES = Gauge(
    'pause_messages',
    'Guardians pause messages',
    ['address', 'version'],
    namespace=PREFIX,
)
PING_MESSAGES = Gauge(
    'ping_messages',
    'Guardians ping messages',
    ['address', 'version'],
    namespace=PREFIX,
)

CURRENT_QUORUM_SIZE = Gauge(
    'quorum_size',
    'Current quorum size',
    namespace=PREFIX,
)

DEPOSITABLE_ETHER = Gauge(
    'depositable_ether',
    'Depositable Ether',
    ['module_id'],
    namespace=PREFIX,
)
POSSIBLE_DEPOSITS_AMOUNT = Gauge(
    'possible_deposits_amount',
    'Possible deposits amount.',
    ['module_id'],
    namespace=PREFIX,
)

ETH_RPC_REQUESTS_DURATION = Histogram(
    'eth_rpc_requests_duration',
    'Duration of requests to ETH1 RPC',
    namespace=PREFIX
)

ETH_RPC_REQUESTS = Counter(
    'eth_rpc_requests',
    'Total count of requests to ETH1 RPC',
    ['method', 'code', 'domain'],
    namespace=PREFIX
)
