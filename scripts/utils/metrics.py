from prometheus_client.metrics import Gauge, Counter


DEPOSITOR_PREFIX = 'depositor_bot_'

BUILD_INFO = Gauge(f'{DEPOSITOR_PREFIX}build_info', 'Build info', [
    'name',
    'network',
    'max_gas_fee',
    'max_buffered_matics',
    'contract_gas_limit',
    'gas_fee_percentile_1',
    'gas_fee_percentile_days_history_1',
    'gas_fee_percentile_2',
    'gas_fee_percentile_days_history_2',
    'gas_priority_fee_percentile',
    'min_priority_fee',
    'max_priority_fee',
    'account_address',
    'create_transactions'
])

GAS_FEE = Gauge(f'{DEPOSITOR_PREFIX}gas_fee', 'Gas fee', ['type'])

DELEGATE_FAILURE = Counter(f'{DEPOSITOR_PREFIX}delegate_failure', 'Delegate failure')
SUCCESS_DELEGATE = Counter(f'{DEPOSITOR_PREFIX}delegate_success', 'Delegate done')

DISTIBUTE_REWARDS_FAILURE = Counter(f'{DEPOSITOR_PREFIX}distribute_rewards_failure', 'Distribute rewards failure')
SUCCESS_DISTIBUTE_REWARDS = Counter(f'{DEPOSITOR_PREFIX}distribute_rewards_success', 'Distribute rewards done')

ACCOUNT_BALANCE = Gauge(f'{DEPOSITOR_PREFIX}account_balance', 'Account balance')

BUFFERED_MATIC = Gauge(f'{DEPOSITOR_PREFIX}buffered_matic', 'Buffered MATIC')
REQUIRED_BUFFERED_MATIC = Gauge(f'{DEPOSITOR_PREFIX}required_buffered_matic', 'Min buffered MATIC amount required for delegate')
CREATING_TRANSACTIONS = Gauge(f'{DEPOSITOR_PREFIX}creating_transactions', 'Creating transactions', ['bot'])

REWARDS_MATIC = Gauge(f'{DEPOSITOR_PREFIX}rewards_matic', 'Rewards MATIC')
REQUIRED_REWARDS_MATIC = Gauge(f'{DEPOSITOR_PREFIX}required_rewards_matic', 'Min rewards MATIC amount required for distribute')
