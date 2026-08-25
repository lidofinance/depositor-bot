import logging
import time
from collections.abc import Callable
from typing import cast

from web3.types import Wei

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

        candidates: list[TopUpCandidate] = []
        for pubkey in pubkeys:
            # Budget spent — the contract funds the queue in order and reverts a sub-minimum tail, so
            # stop before taking a key the leftover can't fund to at least the minimum.
            if remaining < min_top_up_gwei:
                logger.info({'msg': 'CSM top-up: module allocation spent, stop.', 'module_id': module_id, 'selected': len(candidates)})
                break
            lido_key = key_by_pubkey.get(_pubkey_hex(pubkey))
            validator_index = beacon_data.pubkey_to_index.get(pubkey)
            # A key must resolve in both sources to build a proof; otherwise skip it (data
            # availability, not eligibility) so build_topup_proofs never KeyErrors on it.
            if lido_key is None or validator_index is None:
                logger.info(
                    {
                        'msg': 'CSM top-up key skipped — not resolvable.',
                        'module_id': module_id,
                        'pubkey': _pubkey_hex(pubkey),
                        'in_keys_api': lido_key is not None,
                        'in_beacon_state': validator_index is not None,
                    }
                )
                continue
            pending = beacon_data.pending_deposits.get(pubkey, 0)
            balance = beacon_data.validators_fields[validator_index].effective_balance
            topup_amount = target_balance_gwei - (balance + pending)
            # Already at/near the target cap — the gateway would top up nothing; skip without budget.
            if topup_amount < min_top_up_gwei:
                logger.info({'msg': 'CSM top-up key skipped — already at target.', 'module_id': module_id, 'pubkey': _pubkey_hex(pubkey)})
                continue
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
