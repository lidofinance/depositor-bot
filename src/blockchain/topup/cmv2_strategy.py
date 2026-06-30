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
from metrics.metrics import TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP, TOPUP_CANDIDATES_SELECTED, TOPUP_CONSOLIDATION_FILTERED
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient, LidoKey
from web3.types import Wei

logger = logging.getLogger(__name__)


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
            )
            candidates.extend(selected)
            total_consolidation_filtered += filtered

        # LidoKey instances are no longer needed; free before the memory-heavy proof build.
        del keys_by_operator
        TOPUP_CONSOLIDATION_FILTERED.labels(module_id).set(total_consolidation_filtered)

        # Step 7: TopUpGateway requires strictly ascending validator_indices across operators
        candidates.sort(key=lambda c: c.validator_index)
        # Step 8: limit to max_validators
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
) -> tuple[List[TopUpCandidate], int]:
    """Returns (selected_candidates, consolidation_filtered_count).

    consolidation_filtered_count counts only keys that passed all other eligibility checks but
    were blocked by a pending ConsolidationBus request — not all keys in the pending set.
    """
    consolidation_filtered = 0
    eligible = []
    for key in keys:
        candidate = _check_key_eligibility(key, beacon_data, target_balance_gwei, min_top_up_gwei)
        if candidate is None:
            continue
        if candidate.pubkey in pending_consolidation:
            consolidation_filtered += 1
            continue
        eligible.append(candidate)

    eligible.sort(key=lambda c: c.validator_index)
    return _take_up_to_allocation(eligible, allocation, beacon_data, target_balance_gwei, min_top_up_gwei), consolidation_filtered


def _check_key_eligibility(
    key: LidoKey,
    beacon_data: BeaconStateData,
    target_balance_gwei: int,
    min_top_up_gwei: int,
) -> Optional[TopUpCandidate]:
    pubkey = Web3.to_bytes(hexstr=HexStr(key.key))

    validator_index = beacon_data.pubkey_to_index.get(pubkey)
    if validator_index is None:
        return None

    fields = beacon_data.validators_fields[validator_index]
    pending = beacon_data.pending_deposits.get(pubkey, 0)
    current_epoch = beacon_data.slot // SLOTS_PER_EPOCH

    if not _is_active(fields, current_epoch):
        return None
    if _is_slashed(fields):
        return None
    if _is_exiting(fields):
        return None
    if validator_index in beacon_data.consolidation_targets:
        return None
    # Mirror TopUpGateway._evaluateTopUpLimit: a balance above (target - min) leaves less than the
    # minimum meaningful top-up, so the contract would return limit 0 — exclude such keys here too.
    max_eligible_balance_gwei = target_balance_gwei - min_top_up_gwei
    if fields.effective_balance + pending > max_eligible_balance_gwei:
        return None

    return TopUpCandidate(
        validator_index=validator_index,
        key_index=key.index,
        operator_id=key.operatorIndex,
        pubkey=pubkey,
        pending_balance=pending,
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
) -> List[TopUpCandidate]:
    result = []
    remaining = allocation_wei // 10**9
    for c in candidates:
        # Stop before adding a validator the leftover budget can't fund to at least the minimum:
        # the contract spends the allocation in order and tops the last validator up only by what
        # remains — if that is < min it reverts. Checked before append so a sub-min tail is never selected.
        if remaining < min_top_up_gwei:
            break
        balance = beacon_data.validators_fields[c.validator_index].effective_balance
        topup_amount = target_balance_gwei - (balance + c.pending_balance)
        # Already at/near the cap — the contract tops up nothing (mirrors TopUpGateway._evaluateTopUpLimit).
        if topup_amount < min_top_up_gwei:
            continue
        result.append(c)
        # May go negative: the last selected validator absorbs the remaining budget as a partial top-up.
        remaining -= topup_amount
    return result
