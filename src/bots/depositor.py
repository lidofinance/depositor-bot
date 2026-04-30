# pyright: reportTypedDictNotRequiredAccess=false
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple, cast

import variables
from blockchain.contracts.base_interface import ContractInterface
from blockchain.contracts.staking_router import StakingRouterContractV4
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
        self._check_balance()

        sr_version = self.w3.lido.staking_router.get_contract_version()
        if sr_version < 4:
            logger.info({'msg': 'SR version < 4, execute legacy', 'value': sr_version})
            return self._execute_legacy()

        return self._execute_actual()

    def _execute_legacy(self) -> bool:
        modules_to_deposit = self._get_preferred_to_deposit_modules()

        for module_id in modules_to_deposit:
            logger.info({'msg': f'Do deposit to module with id: {module_id}.'})

            result = self._deposit_to_module(module_id, is_top_up_allocation=False)
            logger.info(
                {
                    'msg': f'Deposit status to Module[{module_id}]: {result}.',
                    'value': result,
                }
            )

            if result:
                return result

        return False

    def _execute_actual(self) -> bool:
        modules = self._prefered_modules()
        for module in modules:
            module_id, _module_address, wc_type, is_top_up = module

            if is_top_up:
                logger.info({'msg': f'Do top-up to module with id: {module_id}.'})
                result = self._top_up_to_module(module)
            else:
                # 0x01 -> full deposit (allocation from getDepositAllocation(eth, True))
                # 0x02 -> seed deposit (allocation from getDepositAllocation(eth, False))
                is_top_up_allocation = wc_type != 2
                logger.info({'msg': f'Do deposit to module with id: {module_id}.'})
                result = self._deposit_to_module(module_id, is_top_up_allocation)

            logger.info({'msg': f'Result for Module[{module_id}]: {result}.', 'value': result})

            if result:
                return result

        return False

    def _top_up_to_module(self, module: tuple[int, str, int, bool]) -> bool:
        # re-check canTopUp
        # module_id, _wc_type, module_address, module_allocation = module
        module_id, module_address, _wc_type, _is_top_up = module

        if not self.w3.lido.topup_gateway.can_top_up(module_id):
            logger.info({'msg': 'canTopUp failed.', 'module_id': module_id})
            return False

        depositable_ether = self.w3.lido.lido.get_depositable_ether()
        if depositable_ether == 0:
            logger.info({'msg': 'No depositable ether for top-up.', 'module_id': module_id})
            return False

        sr_v4 = cast(StakingRouterContractV4, self.w3.lido.staking_router)
        _total, allocated, _new = sr_v4.get_deposit_allocations(depositable_ether, is_top_up=True)
        digests = self.w3.lido.staking_router.get_all_staking_module_digests()
        module_allocation: Wei = Wei(0)
        for i, digest in enumerate(digests):
            if digest[2][0] == module_id:
                module_allocation = allocated[i]
                break
        if module_allocation == 0:
            logger.info({'msg': 'Top-up allocation is zero.', 'module_id': module_id})
            return False

        # determine module type and select strategy
        module_type = self._get_module_type(module_address)
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

        # gas check per module
        if not strategy.is_gas_price_ok():
            logger.info({'msg': 'Gas price too high for top-up.', 'module_id': module_id})
            return False

        max_validators = min(
            variables.MAX_VALIDATORS_PER_TOP_UP,
            self.w3.lido.topup_gateway.get_max_validators_per_top_up(),
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

    MODULE_TYPE_CMV2 = b'curated-onchain-v2'.ljust(32, b'\x00')
    GET_TYPE_ABI = ContractInterface.load_abi('./interfaces/IStakingModule.json')

    def _select_topup_strategy(self, module_type: bytes) -> Optional[TopUpStrategy]:
        if module_type == self.MODULE_TYPE_CMV2:
            return self._cmv2_topup_strategy
        return None

    def _get_module_type(self, module_address: str) -> bytes:
        """Call IStakingModule.getType() on the module contract."""
        module = self.w3.eth.contract(
            address=self.w3.to_checksum_address(module_address),
            abi=self.GET_TYPE_ABI,
        )
        return module.functions.getType().call()

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

        for address in guardians:
            for provider in providers:
                balance = provider.eth.get_balance(address)
                GUARDIAN_BALANCE.labels(address=address, chain_id=provider.eth.chain_id).set(balance)

    def _deposit_to_module(self, module_id: int, is_top_up_allocation: bool) -> bool:
        can_deposit = self.w3.lido.deposit_security_module.can_deposit(module_id)
        logger.info({'msg': 'Can deposit to module.', 'value': can_deposit})

        quorum = self._get_quorum(module_id)
        logger.info({'msg': 'Build quorum.', 'value': quorum})

        strategy = self._select_strategy(module_id)
        gas_is_ok = strategy.is_gas_price_ok(module_id)
        logger.info({'msg': 'Calculate gas recommendations.', 'value': gas_is_ok})

        if is_top_up_allocation:
            # 0x01: keys count derived from getDepositsAllocation(_, True)
            is_deposit_amount_ok = strategy.can_deposit_keys_based_on_allocation(module_id)
        else:
            # 0x02 seed: getStakingModuleMaxDepositsCount - use underhood  getDepositAllocations(eth, False) / 32
            is_deposit_amount_ok = strategy.can_deposit_keys_based_on_ether(module_id)
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': is_deposit_amount_ok})

        if can_deposit and quorum and gas_is_ok and is_deposit_amount_ok:
            logger.info({'msg': 'Checks passed. Prepare deposit tx.'})
            success = self.prepare_and_send_tx(module_id, quorum)
            self._flashbots_works = not self._flashbots_works or success
            return success

        logger.info({'msg': 'Checks failed. Skip deposit.'})
        return False

    def _select_strategy(self, module_id) -> DepositStrategy:
        # todo: check by getType
        if module_id == 3:
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

    def _prefered_modules(self) -> list[tuple[int, str, int, bool]]:
        """
        Build a single ordered list of modules to act on.
        Each entry: (module_id, module_address, wc_type, is_top_up).
          is_top_up=True  -> topup path (_top_up_to_module)
          is_top_up=False -> deposit path (_deposit_to_module)
        """
        digests = self.w3.lido.staking_router.get_all_staking_module_digests()

        # gas metrics + quorum heartbeat refresh (single pass for both blocks)
        now = datetime.now()
        for digest in digests:
            module_id = digest[2][0]
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            # Just for metrics
            self._select_strategy(module_id).is_gas_price_ok(module_id)

            if self._get_quorum(module_id):
                self._module_last_heart_beat[module_id] = now

        depositable_ether = self.w3.lido.lido.get_depositable_ether()
        if depositable_ether == 0:
            logger.info({'msg': 'No depositable ether.'})
            return []

        sr_v4 = cast(StakingRouterContractV4, self.w3.lido.staking_router)
        _seed_total, seed_allocated, seed_new = sr_v4.get_deposit_allocations(depositable_ether, is_top_up=False)
        _full_total, full_allocated, full_new = sr_v4.get_deposit_allocations(depositable_ether, is_top_up=True)

        seed_list, seed_has_healthy = self._build_seed_list(digests, seed_allocated, seed_new)
        if seed_has_healthy:
            logger.info({'msg': f'Prefered modules iteration order {seed_list}.'})
            return seed_list

        full_list, _ = self._build_full_list(digests, full_allocated, full_new)
        result = seed_list + full_list
        logger.info({'msg': f'Prefered modules iteration order {result}.'})
        return result

    def _build_seed_list(
        self,
        digests: list,
        allocated: list,
        new_allocations: list,
    ) -> tuple[list[tuple[int, str, int, bool]], bool]:
        """
        Block 1: seed deposits to 0x02 modules using is_top_up=False allocation.
        Returns (candidates, has_healthy):
          has_healthy=True  -> healthy anchor found, list cut up to and including it
          has_healthy=False -> all unhealthy, all candidates returned for second-attempt pass
        """
        candidates: list[tuple[int, str, int, Wei]] = []
        for i, digest in enumerate(digests):
            module_id = digest[2][0]
            wc_type = digest[2][13]
            if wc_type != 2:
                continue
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            if allocated[i] == 0:
                continue
            stake = new_allocations[i] - allocated[i]
            candidates.append((module_id, digest[2][1], wc_type, stake))

        candidates.sort(key=lambda c: c[3])

        result: list[tuple[int, str, int, bool]] = []
        for module_id, module_address, wc_type, _stake in candidates:
            result.append((module_id, module_address, wc_type, False))  # seed -> deposit path
            if self._is_module_healthy(module_id):
                return result, True
        return result, False

    def _build_full_list(
        self,
        digests: list,
        allocated: list,
        new_allocations: list,
    ) -> tuple[list[tuple[int, str, int, bool]], bool]:
        """
        Block 2: full deposits to 0x01 + topups to 0x02 using is_top_up=True allocation.
        Returns (candidates, has_healthy) — same semantics as _build_seed_list.
        """
        candidates: list[tuple[int, str, int, Wei]] = []
        for i, digest in enumerate(digests):
            module_id = digest[2][0]
            wc_type = digest[2][13]
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            if not variables.ENABLE_TOP_UP and wc_type == 2:
                continue
            if allocated[i] == 0:
                continue
            stake = new_allocations[i] - allocated[i]
            candidates.append((module_id, digest[2][1], wc_type, stake))

        candidates.sort(key=lambda c: c[3])

        result: list[tuple[int, str, int, bool]] = []
        for module_id, module_address, wc_type, _stake in candidates:
            is_top_up = wc_type == 2
            result.append((module_id, module_address, wc_type, is_top_up))
            healthy = self.w3.lido.topup_gateway.can_top_up(module_id) if is_top_up else self._is_module_healthy(module_id)
            if healthy:
                return result, True
        return result, False

    def _get_preferred_to_deposit_modules(self) -> list[int]:
        # filter out non allow-listed modules
        module_ids = [
            module_id
            for module_id in self.w3.lido.staking_router.get_staking_module_ids()
            if module_id in variables.DEPOSIT_MODULES_WHITELIST
        ]

        # gather quorum
        now = datetime.now()
        for module_id in module_ids:
            # Just for metrics
            self._select_strategy(module_id).is_gas_price_ok(module_id)

            if self._get_quorum(module_id):
                self._module_last_heart_beat[module_id] = now

        # get digests for all the modules
        module_digests = self.w3.lido.staking_router.get_staking_module_digests(module_ids)
        # sort modules by validator count
        sorted_module_digests = sorted(
            module_digests,
            key=lambda module_digest: self.get_active_validators_count(module_digest),
        )
        # decide if modules are healthy
        # module[2][0] - module_id
        modules_healthiness = [(module[2][0], self._is_module_healthy_keys_amount_check(module[2][0])) for module in sorted_module_digests]

        # take all the modules in sorted order until the first healthy one(including)
        result = self._take_until_first_healthy_module(modules_healthiness)
        logger.info({'msg': f'Legacy module iteration order {result}.'})

        return result

    def _is_module_healthy_keys_amount_check(self, module_id: int) -> bool:
        strategy = self._select_strategy(module_id)
        return self._is_module_healthy(module_id) and strategy.deposited_keys_amount(module_id) >= 1

    def _is_module_healthy(self, module_id: int) -> bool:
        """
        Check quorum and can deposit for non-zero allocation modules
        """
        # Check if the quorum cache is valid
        last_quorum_time = self._module_last_heart_beat[module_id]
        is_valid_quorum = (datetime.now() - last_quorum_time) <= timedelta(minutes=variables.QUORUM_RETENTION_MINUTES)
        logger.info({'msg': f'Is valid quorum {is_valid_quorum}.', 'module_id': module_id})

        # Check if module is available for deposits
        can_deposit = self.w3.lido.deposit_security_module.can_deposit(module_id)
        logger.info({'msg': f'Can deposit {can_deposit}.', 'module_id': module_id})

        return can_deposit and is_valid_quorum

    @staticmethod
    def get_active_validators_count(module: list) -> int:
        total_deposited = module[3][1]  # totalDepositedValidators
        total_exited = module[3][0]  # totalExitedValidators
        return total_deposited - total_exited

    @staticmethod
    def _take_until_first_healthy_module(
        sorted_modules_healthiness: list[Tuple[int, bool]],
    ) -> list[int]:
        module_ids = []
        for module_id, is_healthy in sorted_modules_healthiness:
            module_ids.append(module_id)
            if is_healthy:
                break
        else:
            # If all modules are unhealthy
            return []
        return module_ids
