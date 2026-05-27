# pyright: reportTypedDictNotRequiredAccess=false
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, cast

import variables
from blockchain.contracts.staking_router import MODULE_TYPE_CMV2, MODULE_TYPE_CSM, StakingModuleInfo, StakingRouterContractV4
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
    GUARDIAN_BALANCE,
    MODULE_TX_SEND,
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
        now = datetime.now()
        self._module_last_heart_beat: Dict[int, datetime] = {module_id: now for module_id in variables.DEPOSIT_MODULES_WHITELIST}

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

        sr_version = self.w3.lido.staking_router.get_contract_version()
        logger.info({'msg': 'SR version.', 'value': sr_version})
        result = self._execute_actual()
        logger.info({'msg': 'Depositor iteration finished.', 'value': result})
        return result

    def _execute_actual(self) -> bool:
        digests: list[StakingModuleInfo] = self.w3.lido.staking_router.get_all_staking_module_digests()

        # Step 0: refresh quorum + gas metrics for all whitelisted modules.
        self._refresh_modules_state()

        # Read depositable ether once; if 0 — nothing to do this iteration.
        depositable_ether = self.w3.lido.lido.get_depositable_ether()
        logger.info({'msg': 'Depositable ether.', 'value': depositable_ether})
        if depositable_ether == 0:
            logger.info({'msg': 'No depositable ether — skip iteration.'})
            return False

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

        # Phase A: seed deposits into 0x02 modules.
        logger.info({'msg': 'Phase A start: seed deposits to 0x02 modules.'})
        done, success = self._phase_seed(seed_allocated, seed_new, digests)
        logger.info({'msg': 'Phase A finished.', 'done': done, 'success': success})
        if done:
            return success

        # Phase B: top-ups (0x02) and full deposits (0x01).
        if not variables.ENABLE_TOP_UP:
            logger.info({'msg': 'Phase B start: full deposits to 0x01 (top-up disabled).'})
            _done, success = self._phase_full(seed_allocated, seed_new, digests)
        else:
            logger.info({'msg': 'Phase B start: full deposits to 0x01 + top-up to 0x02.'})
            _done, success = self._phase_full_and_topup(depositable_ether, seed_allocated, seed_new, digests)
        logger.info({'msg': 'Phase B finished.', 'done': _done, 'success': success})
        return success

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

    def _is_in_cooldown(self, module_id: int) -> bool:
        """Quorum-retention cooldown for deposits: we had a quorum within the retention window."""
        last = self._module_last_heart_beat[module_id]
        return (datetime.now() - last) <= timedelta(minutes=variables.QUORUM_RETENTION_MINUTES)

    def _phase_seed(self, seed_allocated: list[int], seed_new: list[int], digests: list[StakingModuleInfo]) -> tuple[bool, bool]:
        """
        Seed deposits into 0x02 modules using is_top_up=False allocations.
        Returns (done, success):
          done=True  -> caller stops (we acted or hit cooldown)
          done=False -> phase produced nothing, caller continues to the next phase
        """
        candidates: list[tuple[int, Wei]] = []
        for i, digest in enumerate(digests):
            module_id = digest['module_id']
            wc_type = digest['wc_type']
            if wc_type != 2:
                continue
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            if seed_allocated[i] == 0:
                continue
            stake = Wei(seed_new[i] - seed_allocated[i])
            candidates.append((module_id, stake))

        candidates.sort(key=lambda c: c[1])
        logger.info(
            {
                'msg': 'Phase A (seed 0x02) candidates sorted by stake asc.',
                'candidates': [{'module_id': c[0], 'stake': int(c[1])} for c in candidates],
            }
        )

        for module_id, _stake in candidates:
            if not self.w3.lido.deposit_security_module.can_deposit(module_id):
                logger.info({'msg': 'Phase A: canDeposit=False — try next module.', 'module_id': module_id})
                continue
            if self._get_quorum(module_id):
                return True, self._deposit_to_module(module_id)
            # No quorum right now: if cooldown is still active, stop and wait for the next bot iteration.
            if self._is_in_cooldown(module_id):
                logger.info({'msg': 'Phase A: no quorum, cooldown active — wait next iteration.', 'module_id': module_id})
                return True, False
            logger.info({'msg': 'Phase A: no quorum, cooldown expired — try next module.', 'module_id': module_id})
        return False, False

    def _phase_full(self, seed_allocated: list[int], seed_new: list[int], digests: list[StakingModuleInfo]) -> tuple[bool, bool]:
        """Full deposits to 0x01 modules using seed (is_top_up=False) allocations."""
        candidates: list[tuple[int, Wei]] = []
        for i, digest in enumerate(digests):
            module_id = digest['module_id']
            wc_type = digest['wc_type']
            if wc_type != 1:
                continue
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            if seed_allocated[i] == 0:
                continue
            stake = Wei(seed_new[i] - seed_allocated[i])
            candidates.append((module_id, stake))

        candidates.sort(key=lambda c: c[1])
        logger.info(
            {
                'msg': 'Phase B (full 0x01) candidates sorted by stake asc.',
                'candidates': [{'module_id': c[0], 'stake': int(c[1])} for c in candidates],
            }
        )

        for module_id, _stake in candidates:
            if not self.w3.lido.deposit_security_module.can_deposit(module_id):
                logger.info({'msg': 'Phase B: canDeposit=False — try next module.', 'module_id': module_id})
                continue
            if self._get_quorum(module_id):
                return True, self._deposit_to_module(module_id)
            if self._is_in_cooldown(module_id):
                logger.info({'msg': 'Phase B: no quorum, cooldown active — wait next iteration.', 'module_id': module_id})
                return True, False
            logger.info({'msg': 'Phase B: no quorum, cooldown expired — try next module.', 'module_id': module_id})
        return False, False

    def _phase_full_and_topup(
        self,
        depositable_ether: Wei,
        seed_allocated: list[int],
        seed_new: list[int],
        digests: list[StakingModuleInfo],
    ) -> tuple[bool, bool]:
        """
        Full deposits to 0x01 + top-ups to 0x02.
        - 0x02 (top-up) candidates: from is_top_up=True allocations (top-up uses its own capacity).
        - 0x01 (full)   candidates: from is_top_up=False (seed) allocations.
        """
        sr_v4 = cast(StakingRouterContractV4, self.w3.lido.staking_router)
        _total, topup_allocated, topup_new = sr_v4.get_deposit_allocations(depositable_ether, is_top_up=True)

        candidates: list[tuple[int, str, int, Wei, Wei]] = []  # (module_id, address, wc_type, stake, topup_allocation)
        for i, digest in enumerate(digests):
            module_id = digest['module_id']
            module_address = digest['address']
            wc_type = digest['wc_type']
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            if wc_type == 2:
                if topup_allocated[i] == 0:
                    continue
                stake = Wei(topup_new[i] - topup_allocated[i])
                candidates.append((module_id, module_address, wc_type, stake, Wei(topup_allocated[i])))
            elif wc_type == 1:
                if seed_allocated[i] == 0:
                    continue
                stake = Wei(seed_new[i] - seed_allocated[i])
                candidates.append((module_id, module_address, wc_type, stake, Wei(0)))

        candidates.sort(key=lambda c: c[3])
        logger.info(
            {
                'msg': 'Phase B (full 0x01 + top-up 0x02) candidates sorted by stake asc.',
                'candidates': [{'module_id': c[0], 'wc_type': c[2], 'stake': int(c[3])} for c in candidates],
            }
        )

        for module_id, module_address, wc_type, _stake, topup_alloc in candidates:
            if wc_type == 2:
                # Top-up path: canTopUp + is_block_distance_passed (no quorum check for top-ups).
                if not self.w3.lido.topup_gateway.can_top_up(module_id):
                    logger.info({'msg': 'Phase B: canTopUp=False — try next module.', 'module_id': module_id})
                    continue
                if not self.w3.lido.topup_gateway.is_block_distance_passed(module_id):
                    logger.info({'msg': 'Phase B: top-up block distance not passed — wait next iteration.', 'module_id': module_id})
                    return True, False
                return True, self._top_up_to_module(module_id, module_address, topup_alloc)
            # 0x01 full deposit path
            if not self.w3.lido.deposit_security_module.can_deposit(module_id):
                logger.info({'msg': 'Phase B: canDeposit=False — try next module.', 'module_id': module_id})
                continue
            if self._get_quorum(module_id):
                return True, self._deposit_to_module(module_id)
            if self._is_in_cooldown(module_id):
                logger.info({'msg': 'Phase B: no quorum, cooldown active — wait next iteration.', 'module_id': module_id})
                return True, False
            logger.info({'msg': 'Phase B: no quorum, cooldown expired — try next module.', 'module_id': module_id})
        return False, False

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
        """New simplified top-up path: gas check (no keys-count) + proof + send. Allocation is passed in."""
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
        )
        if not proof_data:
            logger.info({'msg': 'No top-up candidates.', 'module_id': module_id})
            return False

        tx = self.w3.lido.topup_gateway.top_up(module_id, proof_data)
        success = self.w3.transaction.check(tx) and self.w3.transaction.send(tx, False, 6)
        logger.info({'msg': f'Top-up tx result: {success}.', 'module_id': module_id})
        return success

    def _select_topup_strategy(self, module_type: bytes) -> Optional[TopUpStrategy]:
        if module_type == MODULE_TYPE_CMV2:
            return self._cmv2_topup_strategy
        return None

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

    def _get_quorum(self, module_id: int) -> Optional[List[DepositMessage]]:
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

            if message['depositRoot'] != deposit_root:
                return False

            return True

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
