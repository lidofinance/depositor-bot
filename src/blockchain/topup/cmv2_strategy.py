import logging
import time
from typing import List, Optional, cast

from blockchain.beacon_state.ssz_types import (
    FAR_FUTURE_EPOCH,
    SLOTS_PER_EPOCH,
)
from blockchain.beacon_state.state import BeaconStateData, ValidatorFields, load_beacon_state_data
from blockchain.consolidation.indexer import ConsolidationIndexer
from blockchain.contracts.cmv2 import CMV2Contract
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.strategy import TopUpStrategy
from blockchain.topup.types import TopUpCandidate, TopUpProofData
from blockchain.typings import Web3
from eth_typing import HexStr
from metrics.metrics import (
    TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP,
    TOPUP_CANDIDATES_SELECTED,
    TOPUP_CONSOLIDATION_FILTERED,
    TOPUP_KEY_EXCLUDED,
)
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient, LidoKey
from web3.types import Wei

logger = logging.getLogger(__name__)

# Stable per-key exclusion reasons — used for both the per-cycle log line and TOPUP_KEY_EXCLUDED.
# This is the full answer set for "why wasn't key X topped up this cycle" (see _check_key_eligibility,
# _take_up_to_allocation and the max_validators truncation in get_topup_candidates).
_REASON_NOT_IN_BEACON_STATE = 'not_in_beacon_state'
_REASON_NOT_ACTIVE = 'not_active'
_REASON_SLASHED = 'slashed'
_REASON_EXITING = 'exiting'
_REASON_BEACON_CONSOLIDATION_TARGET = 'beacon_consolidation_target'
_REASON_ALREADY_AT_TARGET_BALANCE = 'already_at_target_balance'
_REASON_PENDING_CONSOLIDATION_BUS = 'pending_consolidation_bus'
_REASON_OPERATOR_BUDGET_EXHAUSTED = 'operator_budget_exhausted'
_REASON_TRUNCATED_BY_MAX_VALIDATORS = 'truncated_by_max_validators'


def _pubkey_hex(pubkey: bytes) -> str:
    return '0x' + pubkey.hex()


def _log_excluded_key(module_id: int, operator_id: int, pubkey: str, reason: str) -> None:
    """One INFO line per excluded top-up candidate — the way to answer "why wasn't key X topped
    up this cycle" for a specific pubkey (grep logs by pubkey). `reason` is also counted in
    TOPUP_KEY_EXCLUDED for trend visibility without per-key cardinality.
    """
    TOPUP_KEY_EXCLUDED.labels(module_id, reason).inc()
    logger.info(
        {
            'msg': 'Top-up candidate excluded.',
            'module_id': module_id,
            'operator_id': operator_id,
            'pubkey': pubkey,
            'reason': reason,
        }
    )


class CMv2TopUpStrategy(TopUpStrategy):
    def get_topup_candidates(
        self,
        keys_api: KeysAPIClient,
        cl: ConsensusClient,
        module_id: int,
        module_address: str,
        module_allocation: Wei,
        max_validators: int,
        consolidation_indexer: ConsolidationIndexer,
    ) -> Optional[TopUpProofData]:
        """Select validators for top-up in a CMv2 module."""
        # Step 1: operator allocation
        cmv2 = cast(
            CMV2Contract,
            self.w3.eth.contract(
                address=self.w3.to_checksum_address(module_address),
                ContractFactoryClass=CMV2Contract,
            ),
        )
        allocated, operator_ids, allocations = cmv2.get_deposits_allocation(module_allocation)

        if allocated == 0:
            now = time.time()
            TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
            TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP.labels(module_id).set(now)
            TOPUP_CONSOLIDATION_FILTERED.labels(module_id).set(0)
            logger.info({'msg': 'No allocation from CMv2.', 'module_id': module_id})
            return None

        allocation_by_operator: dict[int, int] = {op_id: alloc for op_id, alloc in zip(operator_ids, allocations) if alloc > 0}
        if not allocation_by_operator:
            now = time.time()
            TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
            TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP.labels(module_id).set(now)
            TOPUP_CONSOLIDATION_FILTERED.labels(module_id).set(0)
            logger.info({'msg': 'No operators with allocation.', 'module_id': module_id})
            return None

        logger.info(
            {
                'msg': 'CMv2 operator allocations.',
                'module_id': module_id,
                'operators': allocation_by_operator,
            }
        )

        # Step 2: keys from Keys API
        keys_by_operator = keys_api.get_module_operator_used_keys(module_id, list(allocation_by_operator.keys()))

        # Step 3: advance the consolidation base to finalized BEFORE the heavy SSZ load (outside the proof window).
        # Any failure here -> skip the top-up rather than risk topping up a consolidating key.
        try:
            finalized = consolidation_indexer.sync_base_to_finalized()
        except Exception as e:
            logger.error({'msg': 'Consolidation base sync failed — skip top-up.', 'module_id': module_id, 'err': repr(e)})
            return None

        # Step 4: load beacon state (anchors the proof slot; ~2 min)
        all_pubkeys = _collect_pubkeys(keys_by_operator)
        beacon_data = load_beacon_state_data(self.w3, cl, all_pubkeys)

        # Step 5: read the fresh ADD-only tail (finalized -> latest) and build the pending filter set.
        try:
            latest = self.w3.eth.block_number
            pending_consolidation = consolidation_indexer.get_filter_set(finalized + 1, latest)
        except Exception as e:
            logger.error({'msg': 'Consolidation tail read failed — skip top-up.', 'module_id': module_id, 'err': repr(e)})
            return None
        logger.info(
            {
                'msg': 'Consolidation pending filter ready.',
                'module_id': module_id,
                'pending_pubkeys': len(pending_consolidation),
            }
        )

        # Balance limits mirror TopUpGateway._evaluateTopUpLimit (cached on the contract; may change
        # via setTopUpBalanceLimits). A validator whose balance leaves less than min_top_up_gwei of
        # headroom yields an on-chain limit of 0, so we treat target - min as the max eligible balance.
        gateway = self.w3.lido.topup_gateway
        target_balance_gwei = gateway.get_target_balance_gwei()
        min_top_up_gwei = gateway.get_min_top_up_gwei()
        max_eligible_balance_gwei = target_balance_gwei - min_top_up_gwei
        logger.info(
            {
                'msg': 'TopUp balance limits.',
                'target_balance_gwei': target_balance_gwei,
                'min_top_up_gwei': min_top_up_gwei,
                'max_eligible_balance_gwei': max_eligible_balance_gwei,
            }
        )

        # Step 6: select candidates per operator (excluding keys in pending ConsolidationBus requests)
        candidates: list[TopUpCandidate] = []
        total_consolidation_filtered = 0
        for op_id, op_allocation in allocation_by_operator.items():
            selected, filtered = _select_operator_candidates(
                keys_by_operator[op_id],
                op_allocation,
                beacon_data,
                pending_consolidation,
                target_balance_gwei,
                min_top_up_gwei,
                module_id,
            )
            candidates.extend(selected)
            total_consolidation_filtered += filtered

        # LidoKey instances are no longer needed; free before the memory-heavy proof build.
        del keys_by_operator
        TOPUP_CONSOLIDATION_FILTERED.labels(module_id).set(total_consolidation_filtered)

        # Step 7: TopUpGateway requires strictly ascending validator_indices across operators
        candidates.sort(key=lambda c: c.validator_index)
        # Step 8: limit to max_validators — everything past the cap loses purely to cross-operator
        # competition for tx space, not to any eligibility problem of its own.
        for excluded in candidates[max_validators:]:
            _log_excluded_key(module_id, excluded.operator_id, _pubkey_hex(excluded.pubkey), _REASON_TRUNCATED_BY_MAX_VALIDATORS)
        candidates = candidates[:max_validators]
        # Set before the early return so metrics are always fresh after a selection run,
        # including the 0 case — avoids stale values from a previous cycle.
        now = time.time()
        TOPUP_CANDIDATES_SELECTED.labels(module_id).set(len(candidates))
        TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP.labels(module_id).set(now)

        if not candidates:
            logger.info({'msg': 'No eligible candidates.', 'module_id': module_id})
            return None

        logger.info({'msg': 'CMv2 candidates selected.', 'module_id': module_id, 'count': len(candidates)})

        # Step 9: build proofs
        return build_topup_proofs(beacon_data, candidates)


def _collect_pubkeys(keys_by_operator: dict[int, List[LidoKey]]) -> set[bytes]:
    result = set()
    for keys in keys_by_operator.values():
        for k in keys:
            result.add(Web3.to_bytes(hexstr=HexStr(k.key)))
    return result


def _select_operator_candidates(
    keys: List[LidoKey],
    allocation: int,
    beacon_data: BeaconStateData,
    pending_consolidation: set[bytes],
    target_balance_gwei: int,
    min_top_up_gwei: int,
    module_id: int,
) -> tuple[List[TopUpCandidate], int]:
    """Returns (selected_candidates, consolidation_filtered_count).

    consolidation_filtered_count counts only keys that passed all other eligibility checks but
    were blocked by a pending ConsolidationBus request — not all keys in the pending set.
    """
    consolidation_filtered = 0
    eligible = []
    for key in keys:
        candidate, reason = _check_key_eligibility(key, beacon_data, target_balance_gwei, min_top_up_gwei)
        if candidate is None:
            assert reason is not None
            _log_excluded_key(module_id, key.operatorIndex, key.key, reason)
            continue
        if candidate.pubkey in pending_consolidation:
            consolidation_filtered += 1
            _log_excluded_key(module_id, candidate.operator_id, key.key, _REASON_PENDING_CONSOLIDATION_BUS)
            continue
        eligible.append(candidate)

    eligible.sort(key=lambda c: c.validator_index)
    selected = _take_up_to_allocation(eligible, allocation, beacon_data, target_balance_gwei, min_top_up_gwei, module_id)
    return selected, consolidation_filtered


def _check_key_eligibility(
    key: LidoKey,
    beacon_data: BeaconStateData,
    target_balance_gwei: int,
    min_top_up_gwei: int,
) -> tuple[Optional[TopUpCandidate], Optional[str]]:
    """Returns (candidate, exclusion_reason) — reason is set only when candidate is None."""
    pubkey = Web3.to_bytes(hexstr=HexStr(key.key))

    validator_index = beacon_data.pubkey_to_index.get(pubkey)
    if validator_index is None:
        return None, _REASON_NOT_IN_BEACON_STATE

    fields = beacon_data.validators_fields[validator_index]
    pending = beacon_data.pending_deposits.get(pubkey, 0)
    current_epoch = beacon_data.slot // SLOTS_PER_EPOCH

    if not _is_active(fields, current_epoch):
        return None, _REASON_NOT_ACTIVE
    if _is_slashed(fields):
        return None, _REASON_SLASHED
    if _is_exiting(fields):
        return None, _REASON_EXITING
    if validator_index in beacon_data.consolidation_targets:
        return None, _REASON_BEACON_CONSOLIDATION_TARGET
    # Mirror TopUpGateway._evaluateTopUpLimit: a balance above (target - min) leaves less than the
    # minimum meaningful top-up, so the contract would return limit 0 — exclude such keys here too.
    max_eligible_balance_gwei = target_balance_gwei - min_top_up_gwei
    if fields.effective_balance + pending > max_eligible_balance_gwei:
        return None, _REASON_ALREADY_AT_TARGET_BALANCE

    return (
        TopUpCandidate(
            validator_index=validator_index,
            key_index=key.index,
            operator_id=key.operatorIndex,
            pubkey=pubkey,
            pending_balance=pending,
        ),
        None,
    )


def _is_active(fields: ValidatorFields, current_epoch: int) -> bool:
    return fields.activation_epoch <= current_epoch


def _is_slashed(fields: ValidatorFields) -> bool:
    return fields.slashed


def _is_exiting(fields: ValidatorFields) -> bool:
    return fields.exit_epoch != FAR_FUTURE_EPOCH


def _take_up_to_allocation(
    candidates: List[TopUpCandidate],
    allocation_wei: int,
    beacon_data: BeaconStateData,
    target_balance_gwei: int,
    min_top_up_gwei: int,
    module_id: int,
) -> List[TopUpCandidate]:
    result = []
    remaining = allocation_wei // 10**9
    for i, c in enumerate(candidates):
        # Stop before adding a validator the leftover budget can't fund to at least the minimum:
        # the contract spends the allocation in order and tops the last validator up only by what
        # remains — if that is < min it reverts. Checked before append so a sub-min tail is never selected.
        if remaining < min_top_up_gwei:
            for excluded in candidates[i:]:
                _log_excluded_key(module_id, excluded.operator_id, _pubkey_hex(excluded.pubkey), _REASON_OPERATOR_BUDGET_EXHAUSTED)
            break
        balance = beacon_data.validators_fields[c.validator_index].effective_balance
        topup_amount = target_balance_gwei - (balance + c.pending_balance)
        # Already at/near the cap — the contract tops up nothing (mirrors TopUpGateway._evaluateTopUpLimit).
        if topup_amount < min_top_up_gwei:
            _log_excluded_key(module_id, c.operator_id, _pubkey_hex(c.pubkey), _REASON_ALREADY_AT_TARGET_BALANCE)
            continue
        result.append(c)
        # May go negative: the last selected validator absorbs the remaining budget as a partial top-up.
        remaining -= topup_amount
    return result
