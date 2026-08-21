import logging
import time
from enum import StrEnum
from typing import cast

from eth_typing import HexStr
from web3.types import Wei

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
from metrics.metrics import (
    TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP,
    TOPUP_CANDIDATES_SELECTED,
    TOPUP_CONSOLIDATION_FILTERED,
    TOPUP_KEY_EXCLUDED,
)
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient, LidoKey

logger = logging.getLogger(__name__)


class TopUpExclusionReason(StrEnum):
    """Stable per-key exclusion reasons — used for both the per-cycle log line and TOPUP_KEY_EXCLUDED.

    This is the full answer set for "why wasn't key X topped up this cycle" (see
    _check_key_eligibility, _take_up_to_allocation and the max_validators truncation in
    get_topup_candidates). A StrEnum member is a plain str at runtime, so it works directly as a
    Prometheus label value and a JSON log field without a separate mapping.
    """

    NOT_IN_BEACON_STATE = 'not_in_beacon_state'
    NOT_ACTIVE = 'not_active'
    SLASHED = 'slashed'
    EXITING = 'exiting'
    BEACON_CONSOLIDATION_TARGET = 'beacon_consolidation_target'
    ALREADY_AT_TARGET_BALANCE = 'already_at_target_balance'
    PENDING_CONSOLIDATION_BUS = 'pending_consolidation_bus'
    OPERATOR_BUDGET_EXHAUSTED = 'operator_budget_exhausted'
    TRUNCATED_BY_MAX_VALIDATORS = 'truncated_by_max_validators'
    CONFLICTING_KEY_RECORD = 'conflicting_key_record'


def _pubkey_hex(pubkey: bytes) -> str:
    return '0x' + pubkey.hex()


def _log_excluded_key(module_id: int, operator_id: int, pubkey: str, reason: TopUpExclusionReason) -> None:
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
    ) -> TopUpProofData | None:
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

        allocation_by_operator: dict[int, int] = {op_id: alloc for op_id, alloc in zip(operator_ids, allocations, strict=True) if alloc > 0}

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
        keys_by_operator = _drop_repeated_pubkeys(keys_by_operator, module_id)

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

        candidates_by_operator: dict[int, list[TopUpCandidate]] = {}
        total_consolidation_filtered = 0

        for op_id, op_allocation in allocation_by_operator.items():
            op_candidates, filtered = _select_operator_candidates(
                keys_by_operator[op_id], op_allocation, beacon_data, pending_consolidation, target_balance_gwei, min_top_up_gwei, module_id
            )
            if op_candidates:
                candidates_by_operator[op_id] = op_candidates

            total_consolidation_filtered += filtered

        # LidoKey instances are no longer needed; free before the memory-heavy proof build.
        del keys_by_operator
        TOPUP_CONSOLIDATION_FILTERED.labels(module_id).set(total_consolidation_filtered)

        # Set before the early return so metrics are always fresh after a selection run,
        # including the 0 case — avoids stale values from a previous cycle.

        if not candidates_by_operator:
            logger.info({'msg': 'No eligible candidates.', 'module_id': module_id})
            return None

        candidates = _distribute(candidates_by_operator, max_validators)
        now = time.time()

        TOPUP_CANDIDATES_SELECTED.labels(module_id).set(len(candidates))
        TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP.labels(module_id).set(now)
        logger.info({'msg': 'CMv2 candidates selected.', 'module_id': module_id, 'count': len(candidates)})

        # Step 7: TopUpGateway requires strictly ascending validator_indices across operators
        candidates.sort(key=lambda c: c.validator_index)
        # Step 8: build proofs
        return build_topup_proofs(beacon_data, candidates)


def _distribute(candidates_by_operator: dict[int, list[TopUpCandidate]], limit: int) -> list[TopUpCandidate]:
    selected: list[TopUpCandidate] = []

    i = 0
    circle = 0
    operators = list(candidates_by_operator.keys())
    while limit > 0 and operators:
        op_id = operators[i]
        candidates = candidates_by_operator[op_id]

        if circle >= len(candidates):
            # op_id no more has candidates
            operators.remove(op_id)
            if i >= len(operators):
                # finished circle
                i = 0
                circle += 1
            continue
        selected.append(candidates[circle])
        limit -= 1

        i += 1
        if i >= len(operators):
            i = 0
            circle += 1
    return selected


def _drop_repeated_pubkeys(keys_by_operator: dict[int, list[LidoKey]], module_id: int) -> dict[int, list[LidoKey]]:
    """Drop every copy of a pubkey the Keys API returned more than once.

    The API's primary key is (index, operatorIndex, moduleAddress) and `key` carries no unique
    constraint, so one pubkey can arrive under several identities: a second key index of the same
    operator, or a second operator. Both rows resolve to the same validator, and TopUpGateway
    requires strictly increasing validatorIndices, so the whole batch would be rejected.

    Every copy is dropped rather than one being picked. Nothing reverts on a wrong pick — the module
    only checks pubkey against (operatorId, keyIndex), and both identities are genuinely on-chain —
    but it caps and credits per key (CuratedModule.allocateDeposits ->
    NodeOperatorOps.capTopUpLimitsByKeyBalance), and only one of the repeated slots belongs to the
    validator that exists. Which one is not derivable from the Keys API fields, so the choice cannot
    be made here and the rest of the batch proceeds without them.
    """
    counts: dict[str, int] = {}
    for keys in keys_by_operator.values():
        for k in keys:
            counts[k.key] = counts.get(k.key, 0) + 1

    result: dict[int, list[LidoKey]] = {}
    for op_id, keys in keys_by_operator.items():
        kept: list[LidoKey] = []
        for k in keys:
            if counts[k.key] > 1:
                _log_excluded_key(module_id, k.operatorIndex, k.key, TopUpExclusionReason.CONFLICTING_KEY_RECORD)
            else:
                kept.append(k)
        result[op_id] = kept
    return result


def _collect_pubkeys(keys_by_operator: dict[int, list[LidoKey]]) -> set[bytes]:
    result = set()
    for keys in keys_by_operator.values():
        for k in keys:
            result.add(Web3.to_bytes(hexstr=HexStr(k.key)))
    return result


def _select_operator_candidates(
    keys: list[LidoKey],
    allocation: int,
    beacon_data: BeaconStateData,
    pending_consolidation: set[bytes],
    target_balance_gwei: int,
    min_top_up_gwei: int,
    module_id: int,
) -> tuple[list[TopUpCandidate], int]:
    """Returns (selected_candidates, consolidation_filtered_count).

    consolidation_filtered_count counts only keys that passed all other eligibility checks but
    were blocked by a pending ConsolidationBus request — not all keys in the pending set.
    """
    consolidation_filtered = 0
    eligible = []
    for key in keys:
        candidate, reason = _build_candidate_if_eligible(key, beacon_data, target_balance_gwei, min_top_up_gwei)
        if candidate is None:
            assert reason is not None
            _log_excluded_key(module_id, key.operatorIndex, key.key, reason)
            continue
        if candidate.pubkey in pending_consolidation:
            consolidation_filtered += 1
            _log_excluded_key(module_id, candidate.operator_id, key.key, TopUpExclusionReason.PENDING_CONSOLIDATION_BUS)
            continue
        eligible.append(candidate)

    eligible.sort(key=lambda c: c.validator_index)
    selected = _take_up_to_allocation(eligible, allocation, beacon_data, target_balance_gwei, min_top_up_gwei, module_id)
    return selected, consolidation_filtered


def _build_candidate_if_eligible(
    key: LidoKey,
    beacon_data: BeaconStateData,
    target_balance_gwei: int,
    min_top_up_gwei: int,
) -> tuple[TopUpCandidate | None, TopUpExclusionReason | None]:
    """Returns (candidate, exclusion_reason) — reason is set only when candidate is None."""
    pubkey = Web3.to_bytes(hexstr=HexStr(key.key))

    validator_index = beacon_data.pubkey_to_index.get(pubkey)
    if validator_index is None:
        return None, TopUpExclusionReason.NOT_IN_BEACON_STATE

    fields = beacon_data.validators_fields[validator_index]
    pending = beacon_data.pending_deposits.get(pubkey, 0)
    current_epoch = beacon_data.slot // SLOTS_PER_EPOCH

    if not _is_active(fields, current_epoch):
        return None, TopUpExclusionReason.NOT_ACTIVE
    if _is_slashed(fields):
        return None, TopUpExclusionReason.SLASHED
    if _is_exiting(fields):
        return None, TopUpExclusionReason.EXITING
    if validator_index in beacon_data.consolidation_targets:
        return None, TopUpExclusionReason.BEACON_CONSOLIDATION_TARGET
    # Mirror TopUpGateway._evaluateTopUpLimit: a balance above (target - min) leaves less than the
    # minimum meaningful top-up, so the contract would return limit 0 — exclude such keys here too.
    max_eligible_balance_gwei = target_balance_gwei - min_top_up_gwei
    if fields.effective_balance + pending > max_eligible_balance_gwei:
        return None, TopUpExclusionReason.ALREADY_AT_TARGET_BALANCE

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
    candidates: list[TopUpCandidate],
    allocation_wei: int,
    beacon_data: BeaconStateData,
    target_balance_gwei: int,
    min_top_up_gwei: int,
    module_id: int,
) -> list[TopUpCandidate]:
    result = []
    remaining = allocation_wei // 10**9
    for i, c in enumerate(candidates):
        # Stop before adding a validator the leftover budget can't fund to at least the minimum:
        # the contract spends the allocation in order and tops the last validator up only by what
        # remains — if that is < min it reverts. Checked before append so a sub-min tail is never selected.
        if remaining < min_top_up_gwei:
            for excluded in candidates[i:]:
                _log_excluded_key(
                    module_id, excluded.operator_id, _pubkey_hex(excluded.pubkey), TopUpExclusionReason.OPERATOR_BUDGET_EXHAUSTED
                )
            break
        balance = beacon_data.validators_fields[c.validator_index].effective_balance
        topup_amount = target_balance_gwei - (balance + c.pending_balance)
        # Already at/near the cap — the contract tops up nothing (mirrors TopUpGateway._evaluateTopUpLimit).
        if topup_amount < min_top_up_gwei:
            _log_excluded_key(module_id, c.operator_id, _pubkey_hex(c.pubkey), TopUpExclusionReason.ALREADY_AT_TARGET_BALANCE)
            continue
        result.append(c)
        # May go negative: the last selected validator absorbs the remaining budget as a partial top-up.
        remaining -= topup_amount
    return result
