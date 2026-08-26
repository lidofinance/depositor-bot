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

    The module exposes a FIFO top-up queue via getKeysForTopUp. We walk it in order and never
    reorder or drop keys:
      - a key not ready yet (still pending on the CL, missing from the Keys API, or not active
        yet) stops the walk — it stays in the queue for a later cycle;
      - a key the gateway tops up by 0 (slashed / exiting / already at target) stays in the batch
        to flush it out of the queue, but spends nothing from the allocation;
      - otherwise we spend the module allocation on it and stop once the leftover can't fund the
        next key.
    The heavy beacon-state read is shared with any other top-up module this cycle via
    ensure_beacon_state().
    """

    def get_topup_candidates(
        self,
        keys_api: KeysAPIClient,
        ensure_beacon_state: Callable[[], BeaconStateData],
        module_id: int,
        module_address: str,
        module_allocation: Wei,
        max_validators: int,
        consolidation_indexer: ConsolidationIndexer,
    ) -> TopUpProofData | None:
        csm = cast(
            CSM02Contract,
            self.w3.eth.contract(
                address=self.w3.to_checksum_address(module_address),
                ContractFactoryClass=CSM02Contract,
            ),
        )
        pubkeys = csm.get_keys_for_top_up(max_validators)

        TOPUP_CANDIDATES_LAST_RUN_TIMESTAMP.labels(module_id).set(time.time())
        if not pubkeys:
            TOPUP_CANDIDATES_SELECTED.labels(module_id).set(0)
            logger.info({'msg': 'No keys from CSM top-up queue.', 'module_id': module_id})
            return None

        # The module returns only pubkeys; resolve (operator_id, key_index) from the Keys API.
        key_by_pubkey = {key.key: key for key in keys_api.get_module_used_keys(module_id)}

        # Shared heavy read (once per iteration), sliced to just the queued pubkeys.
        beacon_data = extract_state_data(ensure_beacon_state(), set(pubkeys))

        # Balance limits mirror TopUpGateway (target it tops validators up to; minimum meaningful
        # top-up). module_allocation is the ETH the StakingRouter routed to this module — a budget we
        # spend in queue order and stop at, exactly like CMv2's _take_up_to_allocation.
        gateway = self.w3.lido.topup_gateway
        target_balance_gwei = gateway.get_target_balance_gwei()
        min_top_up_gwei = gateway.get_min_top_up_gwei()
        remaining = module_allocation // 10**9  # module budget, wei -> gwei

        current_epoch = beacon_data.slot // SLOTS_PER_EPOCH
        candidates: list[TopUpCandidate] = []
        for pubkey in pubkeys:
            # Allocation spent — don't take a key the leftover can't fund. Stop.
            if remaining < min_top_up_gwei:
                logger.info({'msg': 'CSM top-up: module allocation spent, stop.', 'module_id': module_id, 'selected': len(candidates)})
                break

            validator_index = beacon_data.pubkey_to_index.get(pubkey)
            if validator_index is None:
                # Deposited and already queued, but still a pending deposit on the CL (no validator
                # index yet). Leave it in the queue and stop.
                logger.info(
                    {
                        'msg': 'CSM top-up: queued key not on the beacon chain yet — stop.',
                        'module_id': module_id,
                        'pubkey': _pubkey_hex(pubkey),
                    }
                )
                break

            lido_key = key_by_pubkey.get(_pubkey_hex(pubkey))
            if lido_key is None:
                # Not in Keys API — very rare (stale Keys API, or a real inconsistency). Warn and stop.
                logger.warning(
                    {'msg': 'CSM top-up: queued key not in Keys API — stop.', 'module_id': module_id, 'pubkey': _pubkey_hex(pubkey)}
                )
                break

            fields = beacon_data.validators_fields[validator_index]
            if fields.activation_epoch > current_epoch:
                # Not active yet — can't top it up. Keep it in the queue and stop.
                logger.info({'msg': 'CSM top-up: queued key not active yet — stop.', 'module_id': module_id, 'pubkey': _pubkey_hex(pubkey)})
                break

            pending = beacon_data.pending_deposits.get(pubkey, 0)
            # Slashed / exiting / already at target: the gateway tops it up by 0. Keep it in the batch
            # (to flush the queue) but spend no allocation on it.
            topup_amount = target_balance_gwei - (fields.effective_balance + pending)
            if fields.slashed or fields.exit_epoch != FAR_FUTURE_EPOCH or topup_amount < min_top_up_gwei:
                topup_amount = 0

            candidates.append(
                TopUpCandidate(
                    validator_index=validator_index,
                    key_index=lido_key.index,
                    operator_id=lido_key.operatorIndex,
                    pubkey=pubkey,
                    pending_balance=pending,
                )
            )
            remaining -= topup_amount

        TOPUP_CANDIDATES_SELECTED.labels(module_id).set(len(candidates))
        if not candidates:
            logger.info({'msg': 'No resolvable CSM top-up candidates.', 'module_id': module_id})
            return None

        # TopUpGateway requires strictly ascending validator_indices across the batch.
        candidates.sort(key=lambda c: c.validator_index)
        logger.info({'msg': 'CSM candidates selected.', 'module_id': module_id, 'count': len(candidates)})
        return build_topup_proofs(beacon_data, candidates)
