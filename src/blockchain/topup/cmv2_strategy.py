import logging
from typing import List, Optional, cast

from blockchain.beacon_state.ssz_types import (
    FAR_FUTURE_EPOCH,
    SLOTS_PER_EPOCH,
)
from blockchain.beacon_state.state import BeaconStateData, ValidatorFields, load_beacon_state_data
from blockchain.contracts.cmv2 import CMV2Contract
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.strategy import TopUpStrategy
from blockchain.topup.types import TopUpCandidate, TopUpProofData
from blockchain.typings import Web3
from eth_typing import HexStr
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient, LidoKey
from web3.types import Wei

logger = logging.getLogger(__name__)
# todo: maybe read from the contract
MAX_TOP_UP_BALANCE_GWEI = 2_045_750_000_000  # 2045.75 ETH


class CMv2TopUpStrategy(TopUpStrategy):
    def get_topup_candidates(
        self,
        keys_api: KeysAPIClient,
        cl: ConsensusClient,
        module_id: int,
        module_address: str,
        module_allocation: Wei,
        max_validators: int,
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
            logger.info({'msg': 'No allocation from CMv2.', 'module_id': module_id})
            return None

        allocation_by_operator: dict[int, int] = {op_id: alloc for op_id, alloc in zip(operator_ids, allocations) if alloc > 0}
        if not allocation_by_operator:
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

        # Step 3: load beacon state
        all_pubkeys = _collect_pubkeys(keys_by_operator)
        beacon_data = load_beacon_state_data(self.w3, cl, all_pubkeys)

        # Step 4: select candidates per operator
        candidates: list[TopUpCandidate] = []
        for op_id, op_allocation in allocation_by_operator.items():
            candidates.extend(_select_operator_candidates(keys_by_operator[op_id], op_allocation, beacon_data))

        # LidoKey instances are no longer needed; free before the memory-heavy proof build.
        del keys_by_operator

        if not candidates:
            logger.info({'msg': 'No eligible candidates.', 'module_id': module_id})
            return None

        logger.info({'msg': 'CMv2 candidates selected.', 'module_id': module_id, 'count': len(candidates)})

        # Step 5: TopUpGateway requires strictly ascending validator_indices across operators
        candidates.sort(key=lambda c: c.validator_index)
        # Step 6: limit to max_validators
        candidates = candidates[:max_validators]
        # Step 7: build proofs
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
) -> List[TopUpCandidate]:
    eligible = []
    for key in keys:
        candidate = _check_key_eligibility(key, beacon_data)
        if candidate is not None:
            eligible.append(candidate)

    eligible.sort(key=lambda c: c.validator_index)
    return _take_up_to_allocation(eligible, allocation, beacon_data)


def _check_key_eligibility(key: LidoKey, beacon_data: BeaconStateData) -> Optional[TopUpCandidate]:
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
    # TopUpGateway also checks effective balance on-chain
    if fields.effective_balance + pending > MAX_TOP_UP_BALANCE_GWEI:
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
) -> List[TopUpCandidate]:
    result = []
    remaining = allocation_wei // 10**9
    for c in candidates:
        balance = beacon_data.validators_fields[c.validator_index].effective_balance
        topup_amount = MAX_TOP_UP_BALANCE_GWEI - (balance + c.pending_balance)
        if topup_amount <= 0:
            continue
        result.append(c)
        remaining -= topup_amount
        if remaining <= 0:
            break
    return result
