from prometheus_client.metrics import Counter, Gauge, Info
from variables import DEPOSIT_MODULES_WHITELIST, PROMETHEUS_PREFIX, PUBLIC_ENV_VARS

GAS_FEE = Gauge(
    'gas_fee',
    'Gas fee',
    ['type', 'module_id'],
    namespace=PROMETHEUS_PREFIX,
)

TX_SEND = Counter('transactions_send', 'Amount of send transaction from bot.', ['status'], namespace=PROMETHEUS_PREFIX)

# Initialize metrics
TX_SEND.labels('success').inc(0)
TX_SEND.labels('failure').inc(0)

MODULE_TX_SEND = Counter(
    'transactions',
    'Amount of send transactions from depositor bot.',
    ['status', 'module_id'],
    namespace=PROMETHEUS_PREFIX,
)

DEPOSIT_MESSAGES = Gauge(
    'deposit_messages',
    'Guardians deposit messages',
    ['address', 'module_id', 'version', 'transport', 'chain_id'],
    namespace=PROMETHEUS_PREFIX,
)
PAUSE_MESSAGES = Gauge(
    'pause_messages',
    'Guardians pause messages',
    ['address', 'module_id', 'version', 'transport', 'chain_id'],
    namespace=PROMETHEUS_PREFIX,
)
PING_MESSAGES = Gauge(
    'ping_messages',
    'Guardians ping messages',
    ['address', 'version', 'transport', 'chain_id'],
    namespace=PROMETHEUS_PREFIX,
)
UNVET_MESSAGES = Gauge(
    'unvet_messages',
    'Guardian unvet messages',
    ['address', 'module_id', 'version', 'transport', 'chain_id'],
    namespace=PROMETHEUS_PREFIX,
)

CURRENT_QUORUM_SIZE = Gauge(
    'quorum_size',
    'Current quorum size',
    ['type'],
    namespace=PROMETHEUS_PREFIX,
)

DEPOSITABLE_ETHER = Gauge(
    'depositable_ether',
    'Depositable Ether',
    namespace=PROMETHEUS_PREFIX,
)

POSSIBLE_DEPOSITS_AMOUNT = Gauge(
    'possible_deposits_amount',
    'Possible deposits amount.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

IS_DEPOSITABLE = Gauge(
    'is_depositable',
    'Represents is_depositable check.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

QUORUM = Gauge(
    'quorum',
    'Represents if quorum could be collected.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

GAS_OK = Gauge(
    'is_gas_ok',
    'Represents is_gas_ok check.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

DEPOSIT_AMOUNT_OK = Gauge(
    'is_deposit_amount_ok',
    'Represents is_deposit_amount_ok check.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

UNEXPECTED_EXCEPTIONS = Counter(
    'unexpected_exceptions',
    'Total count of unexpected exceptions',
    ['type'],
    namespace=PROMETHEUS_PREFIX,
)

# TODO unify ACCOUNT_BALANCE and GUARDIAN_BALANCE
ACCOUNT_BALANCE = Gauge(
    'account_balance',
    'Account balance',
    ['address', 'chain_id'],
    namespace=PROMETHEUS_PREFIX,
)

GUARDIAN_BALANCE = Gauge(
    'guardian_balance',
    'Balance of the guardian',
    ['address', 'chain_id'],
    namespace=PROMETHEUS_PREFIX,
)

MODULES = Gauge('modules', 'Modules gauge', ['module_id'], namespace=PROMETHEUS_PREFIX)

for module_id in DEPOSIT_MODULES_WHITELIST:
    MODULES.labels(module_id).set(1)

# --- Deposit / top-up gate state ---

DEPOSITS_PAUSED = Gauge(
    'deposits_paused',
    '1 when DSM.isDepositsPaused() is true.',
    namespace=PROMETHEUS_PREFIX,
)

TOPUP_GATEWAY_PAUSED = Gauge(
    'topup_gateway_paused',
    '1 when TopUpGateway.isPaused() is true. Only set when ENABLE_TOP_UP=true.',
    namespace=PROMETHEUS_PREFIX,
)

MODULE_STATUS = Gauge(
    'module_status',
    'Staking module status from StakingRouter digest. 0=active 1=deposits_paused 2=stopped',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

# --- Phase outcomes ---
# Values: 0=skipped 1=sent 2=tx_failed 3=wait_distance 4=wait_quorum

PHASE_OUTCOME = Gauge(
    'phase_outcome',
    'Last outcome for a module in a given phase. 0=skipped 1=sent 2=tx_failed 3=wait_distance 4=wait_quorum',
    ['phase', 'module_id'],
    namespace=PROMETHEUS_PREFIX,
)

# --- Quorum state per module ---
# Values: 0=stale 1=retained 2=ready

QUORUM_STATE = Gauge(
    'quorum_state',
    'Guardian quorum state per module. 0=stale 1=retained 2=ready',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

# --- Top-up transactions ---

TOPUP_TX_SEND = Counter(
    'topup_transactions',
    'Top-up transactions attempted by the depositor bot.',
    ['status', 'module_id'],
    namespace=PROMETHEUS_PREFIX,
)

TOPUP_GAS_OK = Gauge(
    'is_topup_gas_ok',
    '1 when gas price is acceptable for a top-up transaction.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

TOPUP_CANDIDATES_SELECTED = Gauge(
    'topup_candidates_selected',
    'Validators selected for top-up after eligibility filtering.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

TOPUP_CONSOLIDATION_FILTERED = Gauge(
    'topup_consolidation_filtered_keys',
    'Keys excluded from top-up because they appear in a pending ConsolidationBus request.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

# --- Consolidation indexer ---

CONSOLIDATION_PENDING_BATCHES = Gauge(
    'consolidation_pending_batches',
    'Open ConsolidationBus batches in the in-memory store.',
    namespace=PROMETHEUS_PREFIX,
)

CONSOLIDATION_PENDING_PUBKEYS = Gauge(
    'consolidation_pending_pubkeys',
    'Pubkeys currently excluded from top-up due to pending consolidation.',
    namespace=PROMETHEUS_PREFIX,
)

CONSOLIDATION_CURSOR_LAG = Gauge(
    'consolidation_cursor_lag_blocks',
    'Blocks between the consolidation indexer cursor and the current finalized block.',
    namespace=PROMETHEUS_PREFIX,
)

INFO = Info(name='build', documentation='Info metric', namespace=PROMETHEUS_PREFIX)
CONVERTED_PUBLIC_ENV = {k: str(v) for k, v in PUBLIC_ENV_VARS.items()}
INFO.info(CONVERTED_PUBLIC_ENV)
