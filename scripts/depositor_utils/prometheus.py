from prometheus_client.metrics import Gauge, Enum, Counter

GAS_FEE = Gauge('gas_fee', 'Gas fee', ['type'])

DEPOSIT_FAILURE = Counter('deposit_failure', 'Deposit failure')
SUCCESS_DEPOSIT = Counter('deposit_success', 'Deposit done')

ACCOUNT_BALANCE = Gauge('account_balance', 'Account balance')

KAFKA_DEPOSIT_MESSAGES = Gauge('kafka_deposit_messages', 'Guardians deposit messages', ['address'])
KAFKA_PAUSE_MESSAGES = Gauge('kafka_pause_messages', 'Guardians pause messages', ['address'])
