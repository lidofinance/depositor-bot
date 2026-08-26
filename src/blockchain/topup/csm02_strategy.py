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

    The module itself picks which validators to top up via getKeysForTopUp — so there is no per-key
    eligibility check here (active/slashed/consolidation/balance): we take the queue as given,
    resolve each pubkey to its operator/key index (Keys API) and validator index + pending deposits
    (beacon state), and build the proofs. The heavy beacon-state read is shared with any other
    top-up module this cycle via ensure_beacon_state().
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
            # Budget spent — the contract funds the queue in order and reverts a sub-minimum tail, so
            # stop before taking a key the leftover can't fund to at least the minimum.
            if remaining < min_top_up_gwei:
                logger.info({'msg': 'CSM top-up: module allocation spent, stop.', 'module_id': module_id, 'selected': len(candidates)})
                break

            lido_key = key_by_pubkey.get(_pubkey_hex(pubkey))
            validator_index = beacon_data.pubkey_to_index.get(pubkey)
            # A queued key MUST exist in both the Keys API and the beacon state — impossible in normal
            # operation. Fail loudly rather than drop it or send a partial FIFO batch.
            if lido_key is None or validator_index is None:
                raise ValueError(
                    f'CSM top-up module {module_id}: queued key {_pubkey_hex(pubkey)} not resolvable '
                    f'(in_keys_api={lido_key is not None}, in_beacon_state={validator_index is not None})'
                )

            fields = beacon_data.validators_fields[validator_index]
            pending = beacon_data.pending_deposits.get(pubkey, 0)
            # We never drop a queued key (FIFO). A key the gateway will top up by 0 on-chain — one not
            # active yet, slashed, exiting, or already at the target cap — still goes into the batch,
            # but counts as spending nothing from the module allocation.
            not_active = fields.activation_epoch > current_epoch
            slashed = fields.slashed
            exiting = fields.exit_epoch != FAR_FUTURE_EPOCH
            topup_amount = target_balance_gwei - (fields.effective_balance + pending)
            if not_active or slashed or exiting or topup_amount < min_top_up_gwei:
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
