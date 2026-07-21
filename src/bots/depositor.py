# pyright: reportTypedDictNotRequiredAccess=false
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import Enum
from typing import NamedTuple, cast

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
    CURRENT_QUORUM_SIZE,
    DEPOSIT_AMOUNT_OK,
    DEPOSITABLE_ETHER,
    GUARDIAN_BALANCE,
    MODULE_TX_SEND,
    POSSIBLE_DEPOSITS_AMOUNT,
    QUORUM,
    UNEXPECTED_EXCEPTIONS,
)
from metrics.transport_message_metrics import message_metrics_filter
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient
from schema import Or, Schema
from transport.msg_providers.onchain_transport import (
    DepositParser,
    OnchainTransportProvider,
    PingParser,
)
from transport.msg_providers.rabbit import MessageType, RabbitProvider
from transport.msg_storage import MessageStorage
from transport.msg_types.common import BotMessage, get_messages_sign_filter
from transport.msg_types.deposit import DepositMessage, DepositMessageSchema
from transport.msg_types.ping import PingMessageSchema, to_check_sum_address
from transport.types import TransportType
from web3.types import BlockData, Wei

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


class QuorumState(Enum):
    READY = 'ready'  # a guardian quorum exists now → deposit
    RETAINED = 'retained'  # no quorum now, but one existed within QUORUM_RETENTION_MINUTES → wait
    STALE = 'stale'  # no quorum and none recently → try the next module


class PhaseOutcome(Enum):
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
        now = datetime.now()
        self._module_last_heart_beat: dict[int, datetime] = {module_id: now for module_id in variables.DEPOSIT_MODULES_WHITELIST}

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
                    parsers_providers=[DepositParser, PingParser],
                    allowed_guardians_provider=self.w3.lido.deposit_security_module.get_guardians,
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

        # isDepositsPaused gates only deposits (depositBufferedEther), not top-ups — read once and use
        # it to drop deposit candidates this iteration while top-ups keep flowing (no need to wait it out).
        deposits_paused = self.w3.lido.deposit_security_module.is_deposits_paused()
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
        # 0x01 while deposits are not paused, 0x02 while top-up is enabled and the gateway is not paused.
        top_up_enabled = variables.ENABLE_TOP_UP and not self.w3.lido.topup_gateway.is_paused()
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
            quorum = self._get_quorum(module_id)
            if quorum:
                self._module_last_heart_beat[module_id] = now
                logger.info({'msg': 'Module has quorum — heartbeat refreshed.', 'module_id': module_id})
            else:
                logger.info({'msg': 'Module has no quorum right now.', 'module_id': module_id})

    def _resolve_quorum(self, module_id: int) -> QuorumState:
        """Read the guardian quorum and apply the retention window (replaces _is_in_cooldown)."""
        if self._get_quorum(module_id):
            return QuorumState.READY
        last = self._module_last_heart_beat[module_id]
        if datetime.now() - last <= timedelta(minutes=variables.QUORUM_RETENTION_MINUTES):
            return QuorumState.RETAINED
        return QuorumState.STALE

    def _try_deposit(self, module_id: int, phase: str) -> PhaseOutcome:
        """One seed/full deposit attempt on a module. SKIPPED → caller tries the next candidate."""
        if not self.w3.lido.deposit_security_module.is_min_deposit_distance_passed(module_id):
            logger.info({'msg': f'{phase}: min deposit distance not passed — wait next iteration.', 'module_id': module_id})
            return PhaseOutcome.WAIT_DISTANCE
        state = self._resolve_quorum(module_id)
        if state is QuorumState.READY:
            return PhaseOutcome.SENT if self._deposit_to_module(module_id) else PhaseOutcome.TX_FAILED
        if state is QuorumState.RETAINED:
            logger.info({'msg': f'{phase}: no quorum, retention active — wait next iteration.', 'module_id': module_id})
            return PhaseOutcome.WAIT_QUORUM
        logger.info({'msg': f'{phase}: no quorum, retention expired — try next module.', 'module_id': module_id})
        return PhaseOutcome.SKIPPED

    def _try_top_up(self, candidate: ModuleCandidate, phase: str) -> PhaseOutcome:
        """One top-up attempt on a 0x02 module (no quorum needed). SKIPPED → caller tries the next candidate."""
        module_id = candidate.module_id
        if not self.w3.lido.topup_gateway.is_block_distance_passed():
            logger.info({'msg': f'{phase}: top-up block distance not passed — wait next iteration.', 'module_id': module_id})
            return PhaseOutcome.WAIT_DISTANCE
        sent = self._top_up_to_module(module_id, candidate.address, candidate.allocation)
        return PhaseOutcome.SENT if sent else PhaseOutcome.TX_FAILED

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
            outcome = self._try_deposit(candidate.module_id, 'Phase A')
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

    def _top_up_to_module(self, module_id: int, module_address: str, module_allocation: Wei) -> bool:
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
            return False

        if not strategy.is_gas_price_ok():
            logger.info({'msg': 'Gas price too high for top-up.', 'module_id': module_id})
            return False

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
            return False

        tx = self.w3.lido.topup_gateway.top_up(module_id, proof_data)
        success = self.w3.transaction.check(tx) and self.w3.transaction.send(tx, False, 6)
        logger.info({'msg': f'Top-up tx result: {success}.', 'module_id': module_id})
        return success

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
        guardians_list = self.w3.lido.deposit_security_module.get_guardians()

        def message_filter(message: DepositMessage) -> bool:
            if message['guardianAddress'] not in guardians_list:
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
        sign_filter = get_messages_sign_filter(prefix)

        return self.message_storage.get_messages_and_actualize(lambda x: sign_filter(x) and actualize_filter(x))
