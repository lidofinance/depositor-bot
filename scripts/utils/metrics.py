from prometheus_client.metrics import Gauge, Counter


DEPOSITOR_PREFIX = 'depositor_bot_'

BUILD_INFO = Gauge(f'{DEPOSITOR_PREFIX}build_info', 'Build info', [
    'name',
    'network',
    'max_gas_fee',
    'contract_gas_limit',
    'min_buffered_ether',
    'gas_fee_percentile',
    'gas_fee_percentile_days_history',
    'gas_priority_fee_percentile',
    'min_priority_fee',
    'max_priority_fee',
    'kafka_topic',
    'account_address',
    'create_transactions',
])

GAS_FEE = Gauge(f'{DEPOSITOR_PREFIX}gas_fee', 'Gas fee', ['type'])

DEPOSIT_FAILURE = Counter(f'{DEPOSITOR_PREFIX}deposit_failure', 'Deposit failure')
SUCCESS_DEPOSIT = Counter(f'{DEPOSITOR_PREFIX}deposit_success', 'Deposit done')

ACCOUNT_BALANCE = Gauge(f'{DEPOSITOR_PREFIX}account_balance', 'Account balance')

KAFKA_DEPOSIT_MESSAGES = Gauge(f'{DEPOSITOR_PREFIX}kafka_deposit_messages', 'Guardians deposit messages', ['address', 'version'])
KAFKA_PAUSE_MESSAGES = Gauge(f'{DEPOSITOR_PREFIX}kafka_pause_messages', 'Guardians pause messages', ['address', 'version'])
KAFKA_PING_MESSAGES = Gauge(f'{DEPOSITOR_PREFIX}kafka_ping_messages', 'Guardians ping messages', ['address', 'version'])

CURRENT_QUORUM_SIZE = Gauge(f'{DEPOSITOR_PREFIX}quorum_size', 'Current quorum size')
BUFFERED_ETHER = Gauge(f'{DEPOSITOR_PREFIX}buffered_ether', 'Buffered ether')
OPERATORS_FREE_KEYS = Gauge(f'{DEPOSITOR_PREFIX}operator_free_keys', 'Has free keys')
CREATING_TRANSACTIONS = Gauge(f'{DEPOSITOR_PREFIX}creating_transactions', 'Creating transactions', ['bot'])
