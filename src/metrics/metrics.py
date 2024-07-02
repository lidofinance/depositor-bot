from prometheus_client.metrics import Counter, Gauge, Histogram
from variables import PROMETHEUS_PREFIX, DEPOSIT_MODULES_WHITELIST

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
    namespace=PROMETHEUS_PREFIX,
)

GAS_FEE = Gauge('gas_fee', 'Gas fee', ['type', 'module_id'], namespace=PROMETHEUS_PREFIX)

TX_SEND = Counter('transactions_send', 'Amount of send transaction from bot.', ['status'], namespace=PROMETHEUS_PREFIX)

# Initialize metrics
TX_SEND.labels('success').inc(0)
TX_SEND.labels('failure').inc(0)

ACCOUNT_BALANCE = Gauge('account_balance', 'Account balance', namespace=PROMETHEUS_PREFIX)

DEPOSIT_MESSAGES = Gauge(
    'deposit_messages',
    'Guardians deposit messages',
    ['address', 'module_id', 'version'],
    namespace=PROMETHEUS_PREFIX,
)
PAUSE_MESSAGES = Gauge(
    'pause_messages',
    'Guardians pause messages',
    ['address', 'module_id', 'version'],
    namespace=PROMETHEUS_PREFIX,
)
PING_MESSAGES = Gauge(
    'ping_messages',
    'Guardians ping messages',
    ['address', 'version'],
    namespace=PROMETHEUS_PREFIX,
)
UNVET_MESSAGES = Gauge('unvet_messages', 'Guardian unvet messages', ['address', 'module_id', 'version'])

CURRENT_QUORUM_SIZE = Gauge(
    'quorum_size',
    'Current quorum size',
    ['type'],
    namespace=PROMETHEUS_PREFIX,
)

DEPOSITABLE_ETHER = Gauge(
    'depositable_ether',
    'Depositable Ether',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

POSSIBLE_DEPOSITS_AMOUNT = Gauge(
    'possible_deposits_amount',
    'Possible deposits amount.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

MELLOW_VAULT_BALANCE = Gauge(
    'mellow_vault_balance',
    'Mellow vault balance.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

ETH_RPC_REQUESTS_DURATION = Histogram('eth_rpc_requests_duration', 'Duration of requests to ETH1 RPC', namespace=PROMETHEUS_PREFIX)

ETH_RPC_REQUESTS = Counter(
    'eth_rpc_requests', 'Total count of requests to ETH1 RPC', ['method', 'code', 'domain'], namespace=PROMETHEUS_PREFIX
)

UNEXPECTED_EXCEPTIONS = Counter(
    'unexpected_exceptions',
    'Total count of unexpected exceptions',
    ['type'],
    namespace=PROMETHEUS_PREFIX,
)

MODULES = Gauge('modules', 'Modules gauge', ['module_id'], namespace=PROMETHEUS_PREFIX)

for module_id in DEPOSIT_MODULES_WHITELIST:
    MODULES.labels(module_id).set(1)
