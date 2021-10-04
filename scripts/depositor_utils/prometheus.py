from prometheus_client.metrics import Gauge, Enum, Counter

GAS_FEE = Gauge('gas_fee', 'Gas fee', ['type'])

OPERATORS_FREE_KEYS = Gauge('operator_free_keys', 'Keys that could be deposited')
BUFFERED_ETHER = Gauge('buffered_ether', 'Get total buffered ether')

LIDO_STATUS = Enum('lido_contract_status', 'Lido contract status', states=['stopped', 'active'])

CHECK_FAILURE = Counter('check_failure', 'Deposit pre check failure')
DEPOSIT_FAILURE = Counter('deposit_failure', 'Deposit failure')
SUCCESS_DEPOSIT = Counter('deposit_success', 'Deposit done')

ACCOUNT_BALANCE = Gauge('account_balance', 'Account balance')
