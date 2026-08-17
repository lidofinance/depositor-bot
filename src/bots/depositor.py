# pyright: reportTypedDictNotRequiredAccess=false
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, NamedTuple, cast

from schema import Or, Schema
from web3.types import BlockData, Wei

import variables
from blockchain.consolidation.indexer import ConsolidationIndexer
from blockchain.consolidation.store import InMemoryPendingStore
from blockchain.contracts.consolidation_bus import ConsolidationBusContract
from blockchain.contracts.staking_router import (
    MODULE_TYPE_CMV2,
    MODULE_TYPE_CSM,
    WC_TYPE_0X01,
    WC_TYPE_0X02,
    StakingModuleInfo,
    StakingRouterContractV4,
)
from blockchain.deposit_strategy.base_deposit_strategy import (
    CSMDepositStrategy,
    DefaultDepositStrategy,
)
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from blockchain.deposit_strategy.strategy import DepositStrategy
from blockchain.executor import Executor
from blockchain.topup.cmv2_strategy import CMv2TopUpStrategy
from blockchain.topup.strategy import TopUpStrategy
from blockchain.typings import Web3
from metrics.metrics import (
    ACCOUNT_BALANCE,
    BOT_LAST_CYCLE_TIMESTAMP,
    CURRENT_QUORUM_SIZE,
    DEPOSIT_AMOUNT_OK,
    DEPOSITABLE_ETHER,
    DEPOSITS_PAUSED,
    GUARDIAN_BALANCE,
    MODULE_ALLOCATION,
    MODULE_QUORUM_LAST_SEEN_TIMESTAMP,
    MODULE_STAKE,
    MODULE_STATUS,
    MODULE_TX_SEND,
    PHASE_LAST_RUN_TIMESTAMP,
    PHASE_OUTCOME,
    POSSIBLE_DEPOSITS_AMOUNT,
    QUORUM,
    QUORUM_STATE,
    TOPUP_EXECUTION_PATH,
    TOPUP_GAS_OK,
    TOPUP_GAS_OK_LAST_RUN_TIMESTAMP,
    TOPUP_GATEWAY_PAUSED,
    TOPUP_TX_SEND,
    UNEXPECTED_EXCEPTIONS,
)
from metrics.transport_message_metrics import message_metrics_filter
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient
from transport.msg_providers.onchain_transport import (
    DepositV1Parser,
    DepositV2Parser,
    OnchainTransportProvider,
    PingParser,
)
from transport.msg_providers.rabbit import MessageType, RabbitProvider
from transport.msg_storage import MessageStorage
from transport.msg_types.common import BotMessage, get_messages_sign_filter
from transport.msg_types.deposit import DepositMessage, DepositMessageSchema
from transport.msg_types.ping import PingMessageSchema, to_check_sum_address
from transport.types import TransportType

logger = logging.getLogger(__name__)


class ModuleCandidate(NamedTuple):
    """Module candidate selected for a deposit/top-up in one bot iteration."""

    digest_index: int  # position in the digests list; stable tie-break for equal-stake candidates
    module_id: int
    wc_type: int
    stake: Wei  # new - allocated: module's allocation level before this round; lower stake → deposit first
    address: str
    # Amount the StakingRouter (SR-lib) allocation algorithm decided should be allocated to this module
    # from the depositable buffer sum. Needed only for top-up; unused for deposits.
    allocation: Wei


class TopUpPath(StrEnum):
    """How `TopUpGateway.topUp` is executed, resolved from on-chain role assignment each cycle.

    Derived from chain state rather than from configuration alone, so moving `TOP_UP_ROLE` from the
    bot's key onto a delegation contract (or back) needs no restart timed to the `grantRole` /
    `revokeRole` transactions — the bot follows the role. The same read also covers the case that
    exists today without any delegation: the key simply not holding the role.

    Values must stay in sync with TOPUP_EXECUTION_PATH.
    """

    DIRECT = 'direct'  # bot's own account holds TOP_UP_ROLE → call topUp() directly
    DELEGATED = 'delegated'  # delegation contract holds it and our key is its active delegate
    NOT_DELEGATE = 'not_delegate'  # delegation holds the role, but our key is not its delegate
    TERMINATED = 'terminated'  # delegation holds the role but is terminated — irreversible
    NO_ROLE = 'no_role'  # neither identity holds TOP_UP_ROLE → every top-up would revert

    @property
    def is_executable(self) -> bool:
        return self in (TopUpPath.DIRECT, TopUpPath.DELEGATED)


class QuorumState(StrEnum):
    """A StrEnum member is a plain str at runtime, so it can be passed straight into
    QUORUM_STATE.state(...) (a prometheus_client.Enum, which stores state as its string value)
    without a separate int-mapping table."""

    READY = 'ready'  # a guardian quorum exists now → deposit
    RETAINED = 'retained'  # no quorum now, but one existed within QUORUM_RETENTION_MINUTES → wait
    STALE = 'stale'  # no quorum and none recently → try the next module


class PhaseOutcome(StrEnum):
    SENT = 'sent'  # deposit/top-up tx sent ok
    TX_FAILED = 'tx_failed'  # deposit/top-up tx failed
    WAIT_DISTANCE = 'wait_distance'  # blocked by min deposit / top-up block distance
    WAIT_QUORUM = 'wait_quorum'  # quorum absent now but retained
    SKIPPED = 'skipped'  # nothing actionable in this phase → caller tries the next phase

    @property
    def is_backoff(self) -> bool:
        """Executor scheduling signal: True → +BLOCKS_BETWEEN_EXECUTION (back off), False → +1 (poll next block).

        Back off after a sent tx (give it time) and on a distance wait (the min deposit / top-up block
        distance won't clear for a while, so polling every block is wasteful). A quorum-retention wait
        polls every block instead — a quorum can re-form on any block and we want to catch it fast.
        """
        return self in (PhaseOutcome.SENT, PhaseOutcome.WAIT_DISTANCE)


class Phase(StrEnum):
    A = 'A'  # seed deposits to 0x02 modules
    B = 'B'  # top-ups (0x02) and full deposits (0x01)


def run_depositor(w3, keys_api: KeysAPIClient, cl: ConsensusClient):
    logger.info({'msg': 'Initialize Depositor bot.'})
    sender = Sender(w3)
    gas_price_calculator = GasPriceCalculator(w3)
    base_deposit_strategy = DefaultDepositStrategy(w3, gas_price_calculator)
    csm_strategy = CSMDepositStrategy(w3, gas_price_calculator)

    depositor_bot = DepositorBot(w3, sender, base_deposit_strategy, csm_strategy, gas_price_calculator, keys_api, cl)

    e = Executor(
        w3,
        depositor_bot.execute,
        variables.BLOCKS_BETWEEN_EXECUTION,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute depositor as daemon.'})
    e.execute_as_daemon()


class DepositorBot:
    _flashbots_works = True

    def __init__(
        self,
        w3: Web3,
        sender: Sender,
        base_deposit_strategy: DefaultDepositStrategy,
        csm_strategy: CSMDepositStrategy,
        gas_price_calculator: GasPriceCalculator,
        keys_api: KeysAPIClient,
        cl: ConsensusClient,
    ):
        self.w3 = w3
        self._sender = sender
        self._general_strategy = base_deposit_strategy
        self._csm_strategy = csm_strategy
        self._gas_price_calculator = gas_price_calculator
        self._cmv2_topup_strategy = CMv2TopUpStrategy(w3, gas_price_calculator)
        self._keys_api = keys_api
        self._cl = cl
        self._consolidation_indexer = self._build_consolidation_indexer()
        # Resolved once here so it is never unset, then re-resolved every iteration.
        self._topup_path = TopUpPath.DIRECT
        self._validate_topup_delegation()
        now = datetime.now()
        self._module_last_heart_beat: dict[int, datetime] = {module_id: now for module_id in variables.DEPOSIT_MODULES_WHITELIST}
        for module_id in variables.DEPOSIT_MODULES_WHITELIST:
            MODULE_QUORUM_LAST_SEEN_TIMESTAMP.labels(module_id).set(now.timestamp())

        transports = []

        if TransportType.RABBIT in variables.MESSAGE_TRANSPORTS:
            transports.append(
                RabbitProvider(
                    routing_keys=[MessageType.PING, MessageType.DEPOSIT],
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                )
            )

        self._onchain_transport_w3 = None
        if TransportType.ONCHAIN_TRANSPORT in variables.MESSAGE_TRANSPORTS:
            self._onchain_transport_w3 = OnchainTransportProvider.create_onchain_transport_w3()
            transports.append(
                OnchainTransportProvider(
                    w3=self._onchain_transport_w3,
                    onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
                    message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
                    parsers_providers=[DepositV1Parser, DepositV2Parser, PingParser],
                    delegates_provider=self.w3.lido.get_guardian_delegates,
                )
            )

        if not transports:
            logger.warning(
                {
                    'msg': 'No transports found. Dry mode activated.',
                    'value': variables.MESSAGE_TRANSPORTS,
                }
            )

        self.message_storage = MessageStorage(
            transports,
            filters=[
                message_metrics_filter,
                to_check_sum_address,
            ],
        )

    def execute(self, block: BlockData) -> bool:
        logger.info({'msg': 'Depositor iteration start.', 'block_number': block.get('number')})
        self._check_balance()

        result = self._execute_actual()
        BOT_LAST_CYCLE_TIMESTAMP.set(time.time())
        logger.info({'msg': 'Depositor iteration finished.', 'value': result})
        return result

    def _common_preconditions(self) -> bool:
        """Common gates required for ANY deposit/top-up this iteration, checked before module selection.

        On a miss the protocol state is abnormal, so the caller returns False — the Executor then
        re-checks on the very next block (+1), not the BBE backoff: we want to resume the moment the
        state recovers. Logs the failed condition.
        """
        if not self.w3.lido.lido.can_deposit():
            logger.info({'msg': 'Lido.canDeposit() is false.'})
            return False
        if self.w3.lido.deposit_security_module.get_guardian_quorum() == 0:
            logger.info({'msg': 'Guardian quorum is not set in DSM contract (quorum == 0).'})
            return False
        return True

    def _execute_actual(self) -> bool:
        # Step 0: refresh quorum + gas metrics for all whitelisted modules.
        self._refresh_modules_state()

        # isDepositsPaused is read before the depositable-ether guard so DEPOSITS_PAUSED is always
        # current — the pause state is important to monitor even when the buffer is empty.
        deposits_paused = self.w3.lido.deposit_security_module.is_deposits_paused()
        DEPOSITS_PAUSED.set(int(deposits_paused))

        # Top-up subsystem gates, resolved for the same reason DEPOSITS_PAUSED is read here: both hold
        # for all modules and both are what an operator watches to see the bot can still act, so they
        # must not freeze at their last value on the iterations that return early below — an empty
        # buffer is the common idle state, and it would pin them indefinitely. A delegate can be
        # rotated or revoked, and the delegation contract terminated, under a running bot; each turns
        # every top-up into a revert, and this metric is how that gets noticed. Costs at most four
        # `eth_call`s per iteration, on top of the per-module reads `_refresh_modules_state()` already
        # does before the same early returns.
        # Not a gate — an unusable path still lets the tx be built and fail loudly on the dry-run,
        # which says more than skipping early.
        top_up_enabled = False
        if variables.ENABLE_TOP_UP:
            _tg_paused = self.w3.lido.topup_gateway.is_paused()
            TOPUP_GATEWAY_PAUSED.set(int(_tg_paused))
            self._topup_path = self._resolve_topup_path()
            TOPUP_EXECUTION_PATH.state(self._topup_path)
            top_up_enabled = not _tg_paused
        else:
            TOPUP_GATEWAY_PAUSED.set(0)

        # Read depositable ether once; if 0 — nothing to do this iteration.
        depositable_ether = self.w3.lido.lido.get_depositable_ether()
        DEPOSITABLE_ETHER.set(depositable_ether)
        logger.info({'msg': 'Depositable ether.', 'value': depositable_ether})
        if depositable_ether == 0:
            logger.info({'msg': 'No depositable ether — skip iteration.'})
            return False

        # Abnormal protocol state — restart immediately: return False so the Executor re-checks
        # on the next block (not a backoff), to resume as soon as the state recovers.
        if not self._common_preconditions():
            return False

        if deposits_paused:
            logger.info({'msg': 'Deposits are paused in DSM contract — only top-ups this iteration.'})

        # Compute seed allocation once; both phases use it for module ordering.
        sr_v4 = cast(StakingRouterContractV4, self.w3.lido.staking_router)
        _total, seed_allocated, seed_new = sr_v4.get_deposit_allocations(depositable_ether, is_top_up=False)
        logger.info(
            {
                'msg': 'Seed allocations computed.',
                'is_top_up': False,
                'allocated': list(seed_allocated),
                'new': list(seed_new),
            }
        )
        digests: list[StakingModuleInfo] = self.w3.lido.staking_router.get_all_staking_module_digests()
        for digest in digests:
            if digest['module_id'] in variables.DEPOSIT_MODULES_WHITELIST:
                MODULE_STATUS.labels(digest['module_id']).set(digest['status'])
        self._publish_allocation_metrics(digests, seed_allocated, seed_new, 'seed')

        # Per-module deposit metrics from the seed (is_top_up=False) allocation — 32 ETH per validator.
        # Top-up allocations are intentionally excluded here (top-ups aren't 32-ETH deposits).
        for i, digest in enumerate(digests):
            if digest['module_id'] in variables.DEPOSIT_MODULES_WHITELIST:
                possible_deposits = seed_allocated[i] // (32 * 10**18)
                POSSIBLE_DEPOSITS_AMOUNT.labels(digest['module_id']).set(possible_deposits)
                DEPOSIT_AMOUNT_OK.labels(digest['module_id']).set(int(possible_deposits >= 1))

        # Phase A: seed deposits into 0x02 modules (deposits only — skipped while deposits are paused).
        if not deposits_paused:
            logger.info({'msg': 'Phase A start: seed deposits to 0x02 modules.'})
            outcome = self._phase_seed(seed_allocated, seed_new, digests)
            logger.info({'msg': 'Phase A finished.', 'outcome': outcome.value})
            if outcome is not PhaseOutcome.SKIPPED:
                return outcome.is_backoff

        # Phase B: full deposits (0x01) + top-ups (0x02), gated independently inside the phase —
        # 0x01 while deposits are not paused, 0x02 while `top_up_enabled` (resolved above).
        logger.info({'msg': 'Phase B start: full deposits to 0x01 + top-up to 0x02.'})
        outcome = self._phase_full_and_topup(depositable_ether, seed_allocated, seed_new, digests, deposits_paused, top_up_enabled)

        logger.info({'msg': 'Phase B finished.', 'outcome': outcome.value})
        return outcome.is_backoff

    def _refresh_modules_state(self) -> None:
        """Update last-quorum heart_beat (cooldown source) and run gas-price probe for metrics, for all whitelisted modules."""
        now = datetime.now()
        logger.info(
            {
                'msg': 'Refresh modules state (quorum heartbeats + gas metrics).',
                'whitelist': list(variables.DEPOSIT_MODULES_WHITELIST),
            }
        )
        for module_id in variables.DEPOSIT_MODULES_WHITELIST:
            # Probe gas-price strategy purely for metrics — gas is re-checked right before the tx is sent.
            self._select_strategy(module_id).is_gas_price_ok(module_id)
            # Route through _resolve_quorum (not a bare _get_quorum call) so QUORUM_STATE is refreshed
            # for every whitelisted module every cycle — otherwise a module that's never actually
            # attempted this cycle (top-up-only cycle, lost the priority race, zero allocation) leaves
            # QUORUM_STATE stale at whatever it last was.
            state = self._resolve_quorum(module_id)
            if state is QuorumState.READY:
                self._module_last_heart_beat[module_id] = now
                MODULE_QUORUM_LAST_SEEN_TIMESTAMP.labels(module_id).set(now.timestamp())
                logger.info({'msg': 'Module has quorum — heartbeat refreshed.', 'module_id': module_id})
            else:
                logger.info({'msg': 'Module has no quorum right now.', 'module_id': module_id})

    def _resolve_quorum(self, module_id: int) -> QuorumState:
        """Read the guardian quorum and apply the retention window (replaces _is_in_cooldown)."""
        if self._get_quorum(module_id):
            QUORUM_STATE.labels(module_id).state(QuorumState.READY)
            return QuorumState.READY
        last = self._module_last_heart_beat[module_id]
        if datetime.now() - last <= timedelta(minutes=variables.QUORUM_RETENTION_MINUTES):
            QUORUM_STATE.labels(module_id).state(QuorumState.RETAINED)
            return QuorumState.RETAINED
        QUORUM_STATE.labels(module_id).state(QuorumState.STALE)
        return QuorumState.STALE

    def _try_deposit(self, module_id: int, phase: Phase) -> PhaseOutcome:
        """One seed/full deposit attempt on a module. SKIPPED → caller tries the next candidate."""
        if not self.w3.lido.deposit_security_module.is_min_deposit_distance_passed(module_id):
            logger.info({'msg': f'Phase {phase}: min deposit distance not passed — wait next iteration.', 'module_id': module_id})
            outcome = PhaseOutcome.WAIT_DISTANCE
        else:
            state = self._resolve_quorum(module_id)
            if state is QuorumState.READY:
                outcome = PhaseOutcome.SENT if self._deposit_to_module(module_id) else PhaseOutcome.TX_FAILED
            elif state is QuorumState.RETAINED:
                logger.info({'msg': f'Phase {phase}: no quorum, retention active — wait next iteration.', 'module_id': module_id})
                outcome = PhaseOutcome.WAIT_QUORUM
            else:
                logger.info({'msg': f'Phase {phase}: no quorum, retention expired — try next module.', 'module_id': module_id})
                outcome = PhaseOutcome.SKIPPED
        now = time.time()
        PHASE_OUTCOME.labels(phase, module_id).state(outcome)
        PHASE_LAST_RUN_TIMESTAMP.labels(phase, module_id).set(now)
        return outcome

    def _try_top_up(self, candidate: ModuleCandidate, phase: Phase) -> PhaseOutcome:
        """One top-up attempt on a 0x02 module (no quorum needed). SKIPPED → caller tries the next candidate."""
        module_id = candidate.module_id
        if not self.w3.lido.topup_gateway.is_block_distance_passed():
            logger.info({'msg': f'Phase {phase}: top-up block distance not passed — wait next iteration.', 'module_id': module_id})
            outcome = PhaseOutcome.WAIT_DISTANCE
        else:
            outcome = self._top_up_to_module(module_id, candidate.address, candidate.allocation)
        now = time.time()
        PHASE_OUTCOME.labels(phase, module_id).state(outcome)
        PHASE_LAST_RUN_TIMESTAMP.labels(phase, module_id).set(now)
        return outcome

    def _publish_allocation_metrics(
        self, digests: list[StakingModuleInfo], allocated: list[int], new: list[int], kind: Literal['seed', 'topup']
    ) -> None:
        """Expose allocation/stake for every whitelisted module, not just ones that make it into
        candidates — a module excluded by zero allocation would otherwise keep showing whatever
        outcome it last had, which misrepresents why it isn't being deposited to."""
        for i, digest in enumerate(digests):
            module_id = digest['module_id']
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            MODULE_ALLOCATION.labels(module_id, kind).set(allocated[i])
            MODULE_STAKE.labels(module_id, kind).set(new[i] - allocated[i])

    def _collect_candidates(
        self, digests: list[StakingModuleInfo], wc_type: int, allocated: list[int], new: list[int]
    ) -> list[ModuleCandidate]:
        """Select whitelisted modules of one wc_type that have a non-zero allocation, and build their
        candidate entries (stake = new - allocated, used for ordering).

        Single type per call — the mixed (full + top-up) phase calls it once per type and merges.
        Sorting and logging stay in the caller.
        """
        candidates: list[ModuleCandidate] = []
        for i, digest in enumerate(digests):
            if digest['wc_type'] != wc_type:
                continue
            if digest['module_id'] not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            if digest['status'] != 0:  # only Active modules (replaces SR.canDeposit activity check)
                continue
            if allocated[i] == 0:
                continue
            candidates.append(
                ModuleCandidate(
                    digest_index=i,
                    module_id=digest['module_id'],
                    wc_type=wc_type,
                    stake=Wei(new[i] - allocated[i]),
                    address=digest['address'],
                    allocation=Wei(allocated[i]),
                )
            )
        return candidates

    def _phase_seed(self, seed_allocated: list[int], seed_new: list[int], digests: list[StakingModuleInfo]) -> PhaseOutcome:
        """Seed deposits into 0x02 modules using is_top_up=False allocations.

        SKIPPED -> nothing actionable here, caller continues to the next phase.
        """
        candidates = self._collect_candidates(digests, wc_type=WC_TYPE_0X02, allocated=seed_allocated, new=seed_new)
        candidates.sort(key=lambda c: (c.stake, c.digest_index))
        logger.info(
            {
                'msg': 'Phase A (seed 0x02) candidates sorted by stake asc.',
                'candidates': [{'module_id': c.module_id, 'stake': int(c.stake)} for c in candidates],
            }
        )

        for candidate in candidates:
            outcome = self._try_deposit(candidate.module_id, Phase.A)
            if outcome is not PhaseOutcome.SKIPPED:
                return outcome
        return PhaseOutcome.SKIPPED

    def _phase_full_and_topup(
        self,
        depositable_ether: Wei,
        seed_allocated: list[int],
        seed_new: list[int],
        digests: list[StakingModuleInfo],
        deposits_paused: bool = False,
        top_up_enabled: bool = False,
    ) -> PhaseOutcome:
        """
        Full deposits to 0x01 + top-ups to 0x02, each gated independently:
        - 0x01 (full)   candidates: from is_top_up=False (seed) allocations, only while deposits are not paused.
        - 0x02 (top-up) candidates: from is_top_up=True allocations, only while top-up is enabled/unpaused.
        """
        candidates: list[ModuleCandidate] = []

        if not deposits_paused:
            candidates += self._collect_candidates(digests, wc_type=WC_TYPE_0X01, allocated=seed_allocated, new=seed_new)

        if top_up_enabled:
            sr_v4 = cast(StakingRouterContractV4, self.w3.lido.staking_router)
            _total, topup_allocated, topup_new = sr_v4.get_deposit_allocations(depositable_ether, is_top_up=True)
            self._publish_allocation_metrics(digests, topup_allocated, topup_new, 'topup')
            candidates += self._collect_candidates(digests, wc_type=WC_TYPE_0X02, allocated=topup_allocated, new=topup_new)

        candidates.sort(key=lambda c: (c.stake, c.digest_index))
        logger.info(
            {
                'msg': 'Phase B (full 0x01 + top-up 0x02) candidates sorted by stake asc.',
                'candidates': [{'module_id': c.module_id, 'wc_type': c.wc_type, 'stake': int(c.stake)} for c in candidates],
            }
        )

        for candidate in candidates:
            # The consolidation indexer is guaranteed present and ready in the top-up path — validated
            # at startup when ENABLE_TOP_UP is on (otherwise the bot would not have started).
            if candidate.wc_type == WC_TYPE_0X02:
                outcome = self._try_top_up(candidate, 'Phase B')
            else:
                outcome = self._try_deposit(candidate.module_id, 'Phase B')
            if outcome is not PhaseOutcome.SKIPPED:
                return outcome
        return PhaseOutcome.SKIPPED

    def _deposit_to_module(self, module_id: int) -> bool:
        """New simplified deposit path: gas check (no keys-count) + send."""
        strategy = self._select_strategy(module_id)
        if not strategy.is_gas_price_ok(module_id):
            logger.info({'msg': 'Gas price too high — skip deposit.', 'module_id': module_id})
            return False

        quorum = self._get_quorum(module_id)
        if not quorum:
            logger.info({'msg': 'Quorum disappeared — skip deposit.', 'module_id': module_id})
            return False

        logger.info({'msg': 'Checks passed. Prepare deposit tx.', 'module_id': module_id})
        success = self.prepare_and_send_tx(module_id, quorum)
        self._flashbots_works = not self._flashbots_works or success
        return success

    def _top_up_to_module(self, module_id: int, module_address: str, module_allocation: Wei) -> PhaseOutcome:
        module_type = self.w3.lido.staking_module(module_id).get_type()
        strategy = self._select_topup_strategy(module_type)
        if strategy is None:
            logger.info(
                {
                    'msg': 'Unknown module type, skip.',
                    'module_id': module_id,
                    'type': module_type.rstrip(b'\x00').decode('ascii', errors='replace'),
                }
            )
            return PhaseOutcome.SKIPPED

        gas_ok = strategy.is_gas_price_ok()
        TOPUP_GAS_OK.labels(module_id).set(int(gas_ok))
        TOPUP_GAS_OK_LAST_RUN_TIMESTAMP.labels(module_id).set(time.time())
        if not gas_ok:
            logger.info({'msg': 'Gas price too high for top-up.', 'module_id': module_id})
            return PhaseOutcome.SKIPPED

        max_validators = min(
            variables.MAX_VALIDATORS_PER_TOP_UP,
            self.w3.lido.topup_gateway.get_max_validators_per_top_up(),
        )
        logger.info(
            {
                'msg': 'Top-up: collecting candidates.',
                'module_id': module_id,
                'module_allocation': int(module_allocation),
                'max_validators': max_validators,
            }
        )

        proof_data = strategy.get_topup_candidates(
            self._keys_api,
            self._cl,
            module_id,
            module_address,
            module_allocation,
            max_validators,
            cast(ConsolidationIndexer, self._consolidation_indexer),
        )
        if not proof_data:
            logger.info({'msg': 'No top-up candidates.', 'module_id': module_id})
            return PhaseOutcome.SKIPPED

        tx = self.w3.lido.topup_gateway.top_up(module_id, proof_data)
        # When TOP_UP_ROLE sits on the delegation contract rather than on the bot's key, wrapping must
        # happen before check()/send() so the dry-run and the gas estimate cover the delegated call —
        # the unwrapped one would revert with AccessControlUnauthorizedAccount.
        delegation = self.w3.lido.delegation
        if delegation is not None and self._topup_path is TopUpPath.DELEGATED:
            tx = delegation.wrap(tx)
        success = self.w3.transaction.check(tx) and self.w3.transaction.send(tx, False, 6)
        TOPUP_TX_SEND.labels('success' if success else 'failure', module_id).inc()
        logger.info({'msg': f'Top-up tx result: {success}.', 'module_id': module_id})
        return PhaseOutcome.SENT if success else PhaseOutcome.TX_FAILED

    def _select_topup_strategy(self, module_type: bytes) -> TopUpStrategy | None:
        if module_type == MODULE_TYPE_CMV2:
            return self._cmv2_topup_strategy
        return None

    def _build_consolidation_indexer(self) -> ConsolidationIndexer | None:
        """Build the ConsolidationBus indexer and run the cold-start backfill.

        Top-up needs a ready indexer (to filter keys in pending consolidation requests). So when
        ENABLE_TOP_UP is on the indexer is mandatory: a missing Bus config or a failed cold start
        raises here and the bot does NOT start — fail fast, better than silently skipping every
        top-up until restart. When top-up is disabled the indexer is not needed and stays None.
        """
        if not variables.ENABLE_TOP_UP:
            return None

        address, deploy_block = variables.get_consolidation_bus_config(self.w3.eth.chain_id)
        if address is None or deploy_block is None:
            raise ValueError('ENABLE_TOP_UP is set but ConsolidationBus is not configured for this chain.')

        contract = cast(
            ConsolidationBusContract,
            self.w3.eth.contract(address=address, ContractFactoryClass=ConsolidationBusContract),
        )
        store = InMemoryPendingStore()
        indexer = ConsolidationIndexer(
            self.w3,
            contract,
            store,
            deploy_block,
            variables.CONSOLIDATION_GETLOGS_CHUNK,
        )
        logger.info({'msg': 'ConsolidationBus indexer cold start.', 'address': address, 'deploy_block': deploy_block})
        indexer.cold_start()
        return indexer

    def _resolve_topup_path(self) -> TopUpPath:
        """Resolves how `topUp` must be sent, from who currently holds `TOP_UP_ROLE`.

        Delegation is preferred when it is usable, and the bot's own key is the fallback — so during
        a migration either order of the `grantRole`/`revokeRole` pair keeps working, and neither
        direction needs a restart timed to a block. Re-resolved every cycle and never carried over:
        a delegate can be rotated or revoked, and the contract terminated, under a running bot, and
        each of those turns every top-up into a revert.

        At most three reads (`TOP_UP_ROLE` is a cached constant), so it runs once per iteration
        rather than once per module.

        In dry mode (no account) there is no key to compare against and nothing gets sent, so the
        identity checks are skipped rather than failing the bot.
        """
        gateway = self.w3.lido.topup_gateway
        role = gateway.top_up_role()
        delegation = self.w3.lido.delegation
        blocked: TopUpPath | None = None

        if delegation is not None and gateway.has_role(role, delegation.address):
            if delegation.is_terminated():
                blocked = TopUpPath.TERMINATED
            elif variables.ACCOUNT is None or delegation.get_delegate() == variables.ACCOUNT.address:
                return TopUpPath.DELEGATED
            else:
                blocked = TopUpPath.NOT_DELEGATE
            logger.warning(
                {
                    'msg': 'Delegation contract holds TOP_UP_ROLE but cannot be used. Falling back to a direct call.',
                    'reason': blocked,
                    'delegation': delegation.address,
                }
            )

        if variables.ACCOUNT is None or gateway.has_role(role, variables.ACCOUNT.address):
            return TopUpPath.DIRECT

        return blocked or TopUpPath.NO_ROLE

    def _validate_topup_delegation(self) -> None:
        """Refuse to start when a delegation contract is configured but no path can execute a top-up.

        Same reasoning as the ConsolidationBus indexer: nothing would ever be topped up, and a crash
        loop carrying the reason is far easier to notice than a bot that keeps running quietly.

        Scoped to the case where delegation is configured. `NO_ROLE` without any delegation is the
        pre-existing "role was never granted to the key" misconfiguration — it is now visible on
        `topup_execution_path`, but it must not turn an upgrade of a running deployment into a boot
        failure, so it stays a warning.
        """
        if not variables.ENABLE_TOP_UP:
            return

        self._topup_path = self._resolve_topup_path()
        TOPUP_EXECUTION_PATH.state(self._topup_path)
        if self._topup_path.is_executable:
            logger.info({'msg': 'Top-up execution path resolved.', 'path': self._topup_path})
            return

        account = variables.ACCOUNT.address if variables.ACCOUNT else 'not configured'
        message = (
            f'No usable path for TopUpGateway.topUp: {self._topup_path}. TOP_UP_ROLE must be held either by the '
            f'bot account ({account}) or by delegation contract {variables.DELEGATION_CONTRACT_ADDRESS}, which '
            f'must then be un-terminated with that account as its active delegate.'
        )
        if variables.DELEGATION_CONTRACT_ADDRESS is None:
            logger.warning({'msg': message})
            return
        raise ValueError(message)

    def _check_balance(self):
        if variables.ACCOUNT:
            balance = self.w3.eth.get_balance(variables.ACCOUNT.address)
            ACCOUNT_BALANCE.labels(variables.ACCOUNT.address, self.w3.eth.chain_id).set(balance)
            logger.info({'msg': 'Check account balance.', 'value': balance})

        logger.info({'msg': 'Check guardians balances.'})

        guardians = self.w3.lido.deposit_security_module.get_guardians()
        providers = [self.w3]

        if self._onchain_transport_w3 is not None:
            providers.append(self._onchain_transport_w3)

        new_values = {}
        for address in guardians:
            for provider in providers:
                balance = provider.eth.get_balance(address)
                new_values[(address, provider.eth.chain_id)] = balance

        GUARDIAN_BALANCE.clear()
        for (address, chain_id), balance in new_values.items():
            GUARDIAN_BALANCE.labels(address=address, chain_id=chain_id).set(balance)

    def _select_strategy(self, module_id: int) -> DepositStrategy:
        if self.w3.lido.staking_module(module_id).get_type() == MODULE_TYPE_CSM:
            return self._csm_strategy
        return self._general_strategy

    def _get_quorum(self, module_id: int) -> list[DepositMessage] | None:
        """
        Returns quorum messages or None if the quorum is not ready.
        """
        # Fetch messages and apply filters
        messages = self._fetch_actual_messages()

        # Apply module-specific filtering
        module_filter = self._get_module_messages_filter(module_id)
        filtered_messages = list(filter(module_filter, messages))

        # Get the required quorum size
        min_signs_to_deposit = self.w3.lido.deposit_security_module.get_guardian_quorum()
        CURRENT_QUORUM_SIZE.labels('required').set(min_signs_to_deposit)

        # Group messages by block hash and guardian address
        messages_by_block_hash = defaultdict(dict)
        for message in filtered_messages:
            messages_by_block_hash[message['blockHash']][message['guardianAddress']] = message

        # Evaluate quorum for each block hash
        max_quorum_size = 0
        for guardian_messages in messages_by_block_hash.values():
            unified_messages = list(guardian_messages.values())
            quorum_size = len(unified_messages)

            if quorum_size >= min_signs_to_deposit:
                # Cache and return the quorum
                CURRENT_QUORUM_SIZE.labels('current').set(quorum_size)
                QUORUM.labels(module_id).set(1)
                return unified_messages

            # Track the largest quorum size seen
            max_quorum_size = max(quorum_size, max_quorum_size)

        # Update metrics and indicate no quorum
        CURRENT_QUORUM_SIZE.labels('current').set(max_quorum_size)
        QUORUM.labels(module_id).set(0)
        return None

    def _get_message_actualize_filter(self) -> Callable[[DepositMessage], bool]:
        latest = self.w3.eth.get_block('latest')
        deposit_root = '0x' + self.w3.lido.deposit_contract.get_deposit_root().hex()
        # {delegate_EOA: guardian_contract} at the current block. Rebuilt every cycle so a message
        # whose signer is no longer the guardian's active delegate (rotated, revoked, terminated) is
        # dropped — the off-chain mirror of the on-chain ERC-1271 check, which fails closed.
        delegate_map = self.w3.lido.get_guardian_delegates()
        guardians_list = set(delegate_map.values())

        def message_filter(message: DepositMessage) -> bool:
            delegate = message.get('guardianDelegate')
            if delegate is not None:
                # Data Bus message under the delegation model: the delegate that signed must still be
                # the guardian's active delegate, and still map to the same guardian.
                if delegate_map.get(delegate) != message['guardianAddress']:
                    UNEXPECTED_EXCEPTIONS.labels('unexpected_guardian_address').inc()
                    return False
            elif message['guardianAddress'] not in guardians_list:
                # Legacy path (e.g. RabbitMQ) that carries no delegate: the guardian must still be
                # registered.
                UNEXPECTED_EXCEPTIONS.labels('unexpected_guardian_address').inc()
                return False

            if message['blockNumber'] < latest['number'] - 200:
                return False

            # Message from council is newer than depositor node latest block
            if message['blockNumber'] > latest['number']:
                # can't be verified, so skip
                return True

            return message['depositRoot'] == deposit_root

        return message_filter

    def _get_module_messages_filter(self, module_id: int) -> Callable[[DepositMessage], bool]:
        nonce = self.w3.lido.staking_router.get_staking_module_nonce(module_id)
        return lambda message: message['stakingModuleId'] == module_id and message['nonce'] >= nonce

    def prepare_and_send_tx(self, module_id: int, quorum: list[DepositMessage]) -> bool:
        success = self._sender.prepare_and_send(
            quorum,
            self._flashbots_works,
        )
        logger.info({'msg': f'Tx send. Result is {success}.'})
        label = 'success' if success else 'failure'
        MODULE_TX_SEND.labels(label, module_id).inc()
        return success

    def _fetch_actual_messages(self) -> list[BotMessage]:
        # Fetch messages and apply filters
        actualize_filter = self._get_message_actualize_filter()
        prefix = self.w3.lido.deposit_security_module.get_attest_message_prefix()
        sign_filter = get_messages_sign_filter(prefix, delegated=self.w3.lido.guardian_delegation_active())

        return self.message_storage.get_messages_and_actualize(lambda x: sign_filter(x) and actualize_filter(x))
