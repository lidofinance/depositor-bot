from prometheus_client.metrics import Counter, Gauge, Histogram

from variables import PROMETHEUS_PREFIX

METRICS_PREFIX = PROMETHEUS_PREFIX + '_bot'

BUILD_INFO = Gauge(
    'build_info',
    'Build info',
    [
        'name',
        'max_gas_fee',
        'max_buffered_ethers',
        'contract_gas_limit',
        'gas_fee_percentile_1',
        'gas_fee_percentile_days_history_1',
        'gas_priority_fee_percentile',
        'min_priority_fee',
        'max_priority_fee',
        'account_address',
        'create_transactions',
        'modules_whitelist',
    ],
    namespace=METRICS_PREFIX,
)

GAS_FEE = Gauge('gas_fee', 'Gas fee', ['type', 'module_id'], namespace=METRICS_PREFIX)

TX_SEND = Counter('transactions_send', 'Amount of send transaction from bot.', ['status'], namespace=METRICS_PREFIX)

# Initialize metrics
TX_SEND.labels('success').inc(0)
TX_SEND.labels('failure').inc(0)

ACCOUNT_BALANCE = Gauge('account_balance', 'Account balance', namespace=METRICS_PREFIX)

DEPOSIT_MESSAGES = Gauge(
    'deposit_messages',
    'Guardians deposit messages',
    ['address', 'module_id', 'version'],
    namespace=METRICS_PREFIX,
)
PAUSE_MESSAGES = Gauge(
    'pause_messages',
    'Guardians pause messages',
    ['address', 'module_id', 'version'],
    namespace=METRICS_PREFIX,
)
PING_MESSAGES = Gauge(
    'ping_messages',
    'Guardians ping messages',
    ['address', 'version'],
    namespace=METRICS_PREFIX,
)
UNVET_MESSAGES = Gauge('unvet_messages', 'Guardian unvet messages', ['address', 'module_id', 'version'])

CURRENT_QUORUM_SIZE = Gauge(
    'quorum_size',
    'Current quorum size',
    ['type'],
    namespace=METRICS_PREFIX,
)

DEPOSITABLE_ETHER = Gauge(
    'depositable_ether',
    'Depositable Ether',
    ['module_id'],
    namespace=METRICS_PREFIX,
)

POSSIBLE_DEPOSITS_AMOUNT = Gauge(
    'possible_deposits_amount',
    'Possible deposits amount.',
    ['module_id'],
    namespace=METRICS_PREFIX,
)

ETH_RPC_REQUESTS_DURATION = Histogram('eth_rpc_requests_duration', 'Duration of requests to ETH1 RPC',
                                      namespace=METRICS_PREFIX)

ETH_RPC_REQUESTS = Counter('eth_rpc_requests', 'Total count of requests to ETH1 RPC', ['method', 'code', 'domain'],
                           namespace=METRICS_PREFIX)

UNEXPECTED_EXCEPTIONS = Counter(
    'unexpected_exceptions',
    'Total count of unexpected exceptions',
    ['type'],
    namespace=METRICS_PREFIX,
)
