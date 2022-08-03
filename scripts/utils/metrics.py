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

GAS_FEE = Gauge('gas_fee', 'Gas fee', ['type'], namespace=PREFIX)

DEPOSIT_FAILURE = Counter('deposit_failure', 'Deposit failure', namespace=PREFIX)
SUCCESS_DEPOSIT = Counter('deposit_success', 'Deposit done', namespace=PREFIX)

ACCOUNT_BALANCE = Gauge('account_balance', 'Account balance', namespace=PREFIX)

KAFKA_DEPOSIT_MESSAGES = Gauge(
    'kafka_deposit_messages',
    'Guardians deposit messages',
    ['address', 'version'],
    namespace=PREFIX,
)
KAFKA_PAUSE_MESSAGES = Gauge(
    'kafka_pause_messages',
    'Guardians pause messages',
    ['address', 'version'],
    namespace=PREFIX,
)
KAFKA_PING_MESSAGES = Gauge(
    'kafka_ping_messages',
    'Guardians ping messages',
    ['address', 'version'],
    namespace=PREFIX,
)

CURRENT_QUORUM_SIZE = Gauge(
    'quorum_size',
    'Current quorum size',
    namespace=PREFIX,
)

BUFFERED_ETHER = Gauge('buffered_ether', 'Buffered ether', namespace=PREFIX)
OPERATORS_FREE_KEYS = Gauge('operator_free_keys', 'Has free keys', namespace=PREFIX)
CREATING_TRANSACTIONS = Gauge('creating_transactions', 'Creating transactions', ['bot'], namespace=PREFIX)

REQUIRED_BUFFERED_ETHER = Gauge(
    'required_buffered_ether',
    'Buffered ether amount required for deposit',
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
