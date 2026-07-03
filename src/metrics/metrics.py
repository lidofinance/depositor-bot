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
    '1 when TopUpGateway.isPaused() is true. 0 when ENABLE_TOP_UP=false.',
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

PHASE_LAST_RUN_TIMESTAMP = Gauge(
    'phase_last_run_timestamp_seconds',
    'Unix timestamp of the last time a module was processed in a given phase.',
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
    'topup_gas_ok',
    '1 when gas price is acceptable for a top-up transaction.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

TOPUP_GAS_OK_LAST_RUN_TIMESTAMP = Gauge(
    'topup_gas_ok_last_run_timestamp_seconds',
    'Unix timestamp of the last time the top-up gas check ran for a module.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

TOPUP_CANDIDATES_SELECTED = Gauge(
    'topup_candidates_selected',
    'Validators selected for top-up after eligibility filtering.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP = Gauge(
    'topup_candidates_last_run_timestamp_seconds',
    'Unix timestamp of the last time candidate selection ran for a module.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

TOPUP_CONSOLIDATION_FILTERED = Gauge(
    'topup_consolidation_filtered_keys',
    'Keys excluded from top-up because they appear in a pending ConsolidationBus request.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

# Per-key exclusion reasons. Low cardinality (module_id x ~9 reasons) — use this for trends
# ("why is exclusion rate up"); use the matching per-key log line ('Top-up candidate excluded.')
# to answer "why wasn't key X topped up", since pubkey-labeled Prometheus series would explode
# cardinality. See CMv2TopUpStrategy for the reason values.
TOPUP_KEY_EXCLUDED = Counter(
    'topup_key_excluded',
    'Top-up candidate keys excluded from a top-up tx, by reason.',
    ['module_id', 'reason'],
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

# --- Bot liveness ---

BOT_LAST_CYCLE_TIMESTAMP = Gauge(
    'bot_last_cycle_timestamp_seconds',
    'Unix timestamp of the last time the depositor bot completed a full iteration.',
    namespace=PROMETHEUS_PREFIX,
)

# --- Depositable ether ---

DEPOSITABLE_ETHER = Gauge(
    'depositable_ether',
    'Depositable Ether, read once per bot iteration.',
    namespace=PROMETHEUS_PREFIX,
)

# --- Module priority / allocation ---
# kind: 'seed' (is_top_up=False allocation, used by Phase A 0x02 and Phase B 0x01) or
# 'topup' (is_top_up=True allocation, used by Phase B 0x02). Published for every whitelisted
# module each cycle, including ones excluded from candidates (allocation == 0) — otherwise a
# module with no allocation this cycle keeps showing its last successful outcome forever.

MODULE_ALLOCATION = Gauge(
    'module_allocation_wei',
    'Ether allocation computed by the StakingRouter allocation algorithm for a module this cycle. 0 means the module got no allocation.',
    ['module_id', 'kind'],
    namespace=PROMETHEUS_PREFIX,
)

MODULE_STAKE = Gauge(
    'module_stake_wei',
    'Priority ordering key (new - allocated) for a module; lower value is tried first.',
    ['module_id', 'kind'],
    namespace=PROMETHEUS_PREFIX,
)

# --- Quorum retention ---

MODULE_QUORUM_LAST_SEEN_TIMESTAMP = Gauge(
    'module_quorum_last_seen_timestamp_seconds',
    'Unix timestamp of the last time a guardian quorum was observed for a module. '
    'quorum_state turns stale QUORUM_RETENTION_MINUTES after this.',
    ['module_id'],
    namespace=PROMETHEUS_PREFIX,
)

# --- Top-up gas ---

TOPUP_GAS_FEE = Gauge(
    'topup_gas_fee_wei',
    'Gas fee observed during the top-up gas price check (network-wide, not per-module).',
    ['type'],
    namespace=PROMETHEUS_PREFIX,
)

# --- Keys API freshness ---

KEYS_API_BLOCK_NUMBER = Gauge(
    'keys_api_block_number',
    'elBlockSnapshot.blockNumber from the last successful Keys API response.',
    namespace=PROMETHEUS_PREFIX,
)

KEYS_API_BLOCK_AGE_SECONDS = Gauge(
    'keys_api_block_age_seconds',
    'Seconds between elBlockSnapshot.timestamp of the last Keys API response and now.',
    namespace=PROMETHEUS_PREFIX,
)

# --- Execution layer freshness ---

EL_HEAD_BLOCK_NUMBER = Gauge(
    'el_head_block_number',
    'Latest EL block number seen by the Executor.',
    namespace=PROMETHEUS_PREFIX,
)

EL_HEAD_BLOCK_AGE_SECONDS = Gauge(
    'el_head_block_age_seconds',
    'Seconds between the latest EL block timestamp and now — detects a stalled/lagging RPC.',
    namespace=PROMETHEUS_PREFIX,
)

# --- Pre-initialize series that must exist even before the first bot cycle ---

# Absent counter series cause rate() to return "no data" instead of 0, masking alerts.
for _module_id in DEPOSIT_MODULES_WHITELIST:
    TOPUP_TX_SEND.labels('success', _module_id).inc(0)
    TOPUP_TX_SEND.labels('failure', _module_id).inc(0)
    for _kind in ('seed', 'topup'):
        MODULE_ALLOCATION.labels(_module_id, _kind).set(0)
        MODULE_STAKE.labels(_module_id, _kind).set(0)

# Absent Gauges are indistinguishable from "feature disabled"; 0 is more honest.
DEPOSITS_PAUSED.set(0)
TOPUP_GATEWAY_PAUSED.set(0)
CONSOLIDATION_PENDING_BATCHES.set(0)
CONSOLIDATION_PENDING_PUBKEYS.set(0)
CONSOLIDATION_CURSOR_LAG.set(0)
TOPUP_GAS_FEE.labels('current_fee').set(0)
TOPUP_GAS_FEE.labels('recommended_fee').set(0)
KEYS_API_BLOCK_NUMBER.set(0)
KEYS_API_BLOCK_AGE_SECONDS.set(0)
EL_HEAD_BLOCK_NUMBER.set(0)
EL_HEAD_BLOCK_AGE_SECONDS.set(0)

INFO = Info(name='build', documentation='Info metric', namespace=PROMETHEUS_PREFIX)
CONVERTED_PUBLIC_ENV = {k: str(v) for k, v in PUBLIC_ENV_VARS.items()}
INFO.info(CONVERTED_PUBLIC_ENV)
