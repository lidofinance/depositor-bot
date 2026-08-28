import logging
import time
from collections.abc import Callable
from typing import cast

from web3.types import Wei

from blockchain.beacon_state.ssz_types import FAR_FUTURE_EPOCH, SLOTS_PER_EPOCH
from blockchain.beacon_state.state import BeaconStateData, extract_state_data
from blockchain.consolidation.indexer import ConsolidationIndexer
from blockchain.contracts.csm02 import CSM02Contract
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.strategy import TopUpStrategy
from blockchain.topup.types import TopUpCandidate, TopUpProofData
from metrics.metrics import TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP, TOPUP_CANDIDATES_SELECTED
from providers.keys_api import KeysAPIClient

logger = logging.getLogger(__name__)


def _pubkey_hex(pubkey: bytes) -> str:
    return '0x' + pubkey.hex()


class CSM02TopUpStrategy(TopUpStrategy):
    """Top-up strategy for a community-onchain-v1 (CSM) module with 0x02 withdrawal credentials.

    Bring a single validator per top-up — the queue head — which keeps queue handling simple and
    avoids the validator-index ordering problem for the TopUpGateway input.

    Cases:

    - head is slashed / marked for exit / at target / top-up to reach target < min top-up: the gateway
      sets its limit to 0, so submitting it flushes it from the queue. With budget we flush to reach
      the fundable keys behind it; at zero budget we flush only when the queue is full — the one case
      where it unblocks anything (a full queue caps the module's seed capacity to zero via
      getStakingModuleSummary and blocks all new deposits until the queue is drained);
    - otherwise the head needs a real top-up and allocation >= min top-up: send tx (value top-up);
    - skip: head not on the beacon chain yet / not past its activation epoch / not in the Keys API /
      a fundable head with no budget / a zero-limit head at zero budget while the queue still has room.
    """

    def get_topup_candidates(
        self,
        keys_api: KeysAPIClient,
        ensure_beacon_state: Callable[[], BeaconStateData],
        module_id: int,
        module_address: str,
        module_allocation: Wei,
        max_validators: int,  # unused: CSM brings one key at a time (see class docstring)
        consolidation_indexer: ConsolidationIndexer,  # unused: no CL eligibility checks for CSM
    ) -> TopUpProofData | None:
        csm = cast(
            CSM02Contract,
            self.w3.eth.contract(
                address=self.w3.to_checksum_address(module_address),
                ContractFactoryClass=CSM02Contract,
            ),
        )
        pubkeys = csm.get_keys_for_top_up(1)  # queue head only

        TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP.labels(module_id).set(time.time())
        if not pubkeys:
            TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
            logger.info({'msg': 'No keys from CSM top-up queue.', 'module_id': module_id})
            return None

        pubkey = pubkeys[0]

        # Heavy beacon-state read (once per iteration), sliced to the single queued pubkey.
        beacon_data = extract_state_data(ensure_beacon_state(), {pubkey})

        validator_index = beacon_data.pubkey_to_index.get(pubkey)
        if validator_index is None:
            # Queued, but still a pending deposit on the CL (no validator index yet) — can't prove it.
            # Leave it in the queue for a later cycle.
            TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
            logger.info(
                {
                    'msg': 'CSM top-up: queued key not on the beacon chain yet, skip.',
                    'module_id': module_id,
                    'pubkey': _pubkey_hex(pubkey),
                }
            )
            return None

        # We don't top up validators that are not active yet. A non-active queue head stays in the
        # queue; skip this module and move on to the next.
        fields = beacon_data.validators_fields[validator_index]
        if fields.activation_epoch > beacon_data.slot // SLOTS_PER_EPOCH:
            TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
            logger.info({'msg': 'CSM top-up: queued key not active yet, skip.', 'module_id': module_id, 'pubkey': _pubkey_hex(pubkey)})
            return None

        # The module returns only a pubkey; resolve (operator_id, key_index) from the Keys API.
        lido_key = next((k for k in keys_api.get_module_used_keys(module_id) if k.key == _pubkey_hex(pubkey)), None)
        if lido_key is None:
            TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
            logger.warning({'msg': 'CSM top-up: queued key not in Keys API, skip.', 'module_id': module_id, 'pubkey': _pubkey_hex(pubkey)})
            return None

        # Classify the head against the gateway limit (mirrors TopUpGateway._evaluateTopUpLimit) to
        # pick the flush path from the value path.
        gateway = self.w3.lido.topup_gateway
        target_balance_gwei = gateway.get_target_balance_gwei()
        min_top_up_gwei = gateway.get_min_top_up_gwei()
        pending = beacon_data.pending_deposits.get(pubkey, 0)
        headroom_gwei = target_balance_gwei - (fields.effective_balance + pending)
        # A 0 gateway limit → the module dequeues the head at any budget (flush). Otherwise the head
        # needs a real top-up, which needs allocation.
        head_is_zero_limit = fields.slashed or fields.exit_epoch != FAR_FUTURE_EPOCH or headroom_gwei < min_top_up_gwei

        # No budget for a value top-up. Whether we still submit depends on the head and the queue.
        if module_allocation // 10**9 < min_top_up_gwei:
            if not head_is_zero_limit:
                # Fundable head, nothing to flush — wait for allocation.
                TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
                logger.info(
                    {
                        'msg': 'CSM top-up: fundable head but allocation below a minimal top-up, skip.',
                        'module_id': module_id,
                        'module_allocation': int(module_allocation),
                        'min_top_up_gwei': min_top_up_gwei,
                    }
                )
                return None
            if csm.get_top_up_queue_capacity() > 0:
                # A zero-limit head with a 0 budget is only worth flushing to unblock seed — and seed is
                # blocked only by a full queue. Free seats left → nothing to unblock, don't burn gas.
                TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
                logger.info(
                    {
                        'msg': 'CSM top-up: zero-limit head but queue is not full — no seed to unblock, skip.',
                        'module_id': module_id,
                        'pubkey': _pubkey_hex(pubkey),
                    }
                )
                return None
            # Zero-limit head + full queue → flush to unblock seed (fall through to build).

        candidate = TopUpCandidate(
            validator_index=validator_index,
            key_index=lido_key.index,
            operator_id=lido_key.operatorIndex,
            pubkey=pubkey,
            pending_balance=pending,
        )
        TOPUP_CANDIDATES_SELECTED.labels(module_id).set(1)
        logger.info(
            {
                'msg': 'CSM candidate selected.',
                'module_id': module_id,
                'operator_id': lido_key.operatorIndex,
                'key_index': lido_key.index,
                'validator_index': validator_index,
                'pubkey': _pubkey_hex(pubkey),
                'flush': head_is_zero_limit,
            }
        )
        return build_topup_proofs(beacon_data, [candidate])
