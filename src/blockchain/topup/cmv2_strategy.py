import logging
from typing import List, Optional, cast

from blockchain.beacon_state.ssz_types import (
    FAR_FUTURE_EPOCH,
    SLOTS_PER_EPOCH,
    STATE_BALANCES,
    STATE_VALIDATORS,
    VALIDATOR_ACTIVATION_EPOCH,
    VALIDATOR_EXIT_EPOCH,
    VALIDATOR_SLASHED,
)
from blockchain.beacon_state.state import BeaconStateData, load_beacon_state_data
from blockchain.contracts.cmv2 import CMV2Contract
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.types import TopUpCandidate, TopUpProofData
from blockchain.typings import Web3
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient, LidoKey
from web3.types import Wei

logger = logging.getLogger(__name__)
# todo: maybe read from the contract
MAX_TOP_UP_BALANCE_GWEI = 2_045_750_000_000  # 2045.75 ETH


def get_cmv2_topup_candidates(
    w3: Web3,
    keys_api: KeysAPIClient,
    cl: ConsensusClient,
    module_id: int,
    module_address: str,
    module_allocation: Wei,
) -> Optional[TopUpProofData]:
    """Select validators for top-up in a CMv2 module."""
    # Step 1: operator allocation
    cmv2 = cast(
        CMV2Contract,
        w3.eth.contract(
            address=w3.to_checksum_address(module_address),
            ContractFactoryClass=CMV2Contract,
        ),
    )
    allocated, operator_ids, allocations = cmv2.get_deposits_allocation(module_allocation)

    if allocated == 0:
        logger.info({'msg': 'No allocation from CMv2.', 'module_id': module_id})
        return None

    operators_with_allocation = [(op_id, alloc) for op_id, alloc in zip(operator_ids, allocations) if alloc > 0]
    if not operators_with_allocation:
        logger.info({'msg': 'No operators with allocation.', 'module_id': module_id})
        return None

    logger.info(
        {
            'msg': 'CMv2 operator allocations.',
            'module_id': module_id,
            'operators': operators_with_allocation,
        }
    )

    # Step 2: keys from Keys API
    # TODO: optimize — fetches all module keys then filters by operator
    active_operator_ids = [op_id for op_id, _ in operators_with_allocation]
    keys_by_operator = keys_api.get_module_operator_used_keys(module_id, active_operator_ids)

    # Step 3: load beacon state
    all_pubkeys = _collect_pubkeys(keys_by_operator)
    beacon_data = load_beacon_state_data(w3, cl, all_pubkeys)

    # Step 4: select candidates per operator
    candidates = []
    for op_id, op_allocation in operators_with_allocation:
        op_keys = keys_by_operator[op_id]
        op_candidates = _select_operator_candidates(op_keys, op_allocation, beacon_data)
        candidates.extend(op_candidates)

    if not candidates:
        logger.info({'msg': 'No eligible candidates.', 'module_id': module_id})
        return None

    logger.info({'msg': 'CMv2 candidates selected.', 'module_id': module_id, 'count': len(candidates)})

    # Step 5: build proofs
    return build_topup_proofs(beacon_data, candidates)


def _collect_pubkeys(keys_by_operator: dict[int, List[LidoKey]]) -> set[bytes]:
    result = set()
    for keys in keys_by_operator.values():
        for k in keys:
            result.add(_key_to_bytes(k))
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

    eligible.sort(key=lambda c: c.key_index)
    return _take_up_to_allocation(eligible, allocation, beacon_data)


def _check_key_eligibility(key: LidoKey, beacon_data: BeaconStateData) -> Optional[TopUpCandidate]:
    pubkey = _key_to_bytes(key)

    validator_index = beacon_data.pubkey_to_index.get(pubkey)
    if validator_index is None:
        return None

    validator = beacon_data.state[STATE_VALIDATORS][validator_index]
    # TODO: on contract side check via effective balance, do ween here actual? or need consistency ?
    balance = int(beacon_data.state[STATE_BALANCES][validator_index])
    pending = beacon_data.pending_deposits.get(pubkey, 0)
    current_epoch = beacon_data.slot // SLOTS_PER_EPOCH

    if not _is_active(validator, current_epoch):
        return None
    if _is_slashed(validator):
        return None
    if _is_exiting(validator):
        return None
    if validator_index in beacon_data.consolidation_targets:
        return None
    if balance + pending > MAX_TOP_UP_BALANCE_GWEI:
        return None

    return TopUpCandidate(
        validator_index=validator_index,
        key_index=key.index,
        operator_id=key.operatorIndex,
        pubkey=pubkey,
        pending_balance=pending,
    )


def _is_active(validator, current_epoch: int) -> bool:
    return int(validator[VALIDATOR_ACTIVATION_EPOCH]) <= current_epoch


def _is_slashed(validator) -> bool:
    return bool(validator[VALIDATOR_SLASHED])


def _is_exiting(validator) -> bool:
    return int(validator[VALIDATOR_EXIT_EPOCH]) != FAR_FUTURE_EPOCH


def _take_up_to_allocation(
    candidates: List[TopUpCandidate],
    allocation_wei: int,
    beacon_data: BeaconStateData,
) -> List[TopUpCandidate]:
    result = []
    remaining = allocation_wei // 10**9
    for c in candidates:
        balance = int(beacon_data.state[STATE_BALANCES][c.validator_index])
        topup_amount = MAX_TOP_UP_BALANCE_GWEI - (balance + c.pending_balance)
        if topup_amount <= 0:
            continue
        result.append(c)
        remaining -= topup_amount
        if remaining <= 0:
            break
    return result


def _key_to_bytes(key: LidoKey) -> bytes:
    k = key.key
    if k.startswith('0x'):
        k = k[2:]
    return bytes.fromhex(k)
