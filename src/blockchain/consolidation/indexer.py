# pyright: reportTypedDictNotRequiredAccess=false
"""Pending ConsolidationBus indexer (in-memory).

Two-tier model:
  BASE  (deploy -> finalized): replayed (add + close) into the in-memory store.
                               Advanced at cold start AND before SSZ in every top-up.
  TAIL  (finalized -> latest):  read ephemerally on every top-up, ADD-only, not stored.

Filter set = store.pending_pubkeys() ∪ tail.added_pubkeys.

No persistence: the base lives in memory and is rebuilt from chain on every bot start
(cold_start always replays from deploy_block). Top-up is allowed only when the indexer is
ready and the base reached the current finalized; any failure -> caller skips the top-up.
"""

import logging

from blockchain.consolidation.store import InMemoryPendingStore
from blockchain.contracts.consolidation_bus import ConsolidationBusContract
from blockchain.typings import Web3
from eth_abi.abi import decode as abi_decode
from metrics.metrics import CONSOLIDATION_CURSOR_LAG, CONSOLIDATION_PENDING_BATCHES, CONSOLIDATION_PENDING_PUBKEYS
from web3.types import EventData

logger = logging.getLogger(__name__)

# abi.encode(ConsolidationGroup[]); ConsolidationGroup = (bytes[] sourcePubkeys, bytes targetPubkey)
_BATCH_DATA_ABI = ['(bytes[],bytes)[]']


def _to_hex(value) -> str:
    """bytes-like -> lowercase hex, no 0x."""
    return bytes(value).hex()


class ConsolidationIndexer:
    def __init__(
        self,
        w3: Web3,
        contract: ConsolidationBusContract,
        store: InMemoryPendingStore,
        deploy_block: int,
        chunk: int,
    ):
        self.w3 = w3
        self.contract = contract
        self.store = store
        self.deploy_block = deploy_block
        self.chunk = chunk

    # ---- lifecycle ----
    def cold_start(self) -> None:
        """Full backfill (deploy -> finalized) at bot init.

        Raises on failure — the caller must NOT run a half-initialized indexer (it would skip every
        top-up until restart). The bot fails fast at startup instead.
        """
        finalized = self.sync_base_to_finalized()
        logger.info(
            {
                'msg': 'Consolidation indexer ready.',
                'finalized': finalized,
                'pending_batches': self.store.pending_batch_count(),
                'pending_pubkeys': self.store.pending_pubkey_count(),
            }
        )

    # ---- base (up to finalized) ----
    def sync_base_to_finalized(self) -> int:
        """Advance the in-memory base to the current finalized block. Returns that block."""
        finalized = self._finalized_block()
        start = self.store.get_cursor(default=self.deploy_block - 1) + 1
        if start <= finalized:
            logger.info({'msg': 'Consolidation base sync.', 'from': start, 'to': finalized})
            self._sync_range(start, finalized)
        CONSOLIDATION_PENDING_BATCHES.set(self.store.pending_batch_count())
        CONSOLIDATION_PENDING_PUBKEYS.set(self.store.pending_pubkey_count())
        cursor = self.store.get_cursor(default=self.deploy_block - 1)
        CONSOLIDATION_CURSOR_LAG.set(max(0, finalized - cursor))
        return finalized

    def _sync_range(self, from_block: int, to_block: int) -> None:
        frm = from_block
        while frm <= to_block:
            to = min(frm + self.chunk - 1, to_block)
            self._apply_chunk(frm, to)
            self.store.set_cursor(to)  # advance only after a fully read & applied chunk
            frm = to + 1

    def _apply_chunk(self, from_block: int, to_block: int) -> None:
        added = self.contract.get_requests_added_logs(from_block, to_block)
        executed = self.contract.get_requests_executed_logs(from_block, to_block)
        removed = self.contract.get_batches_removed_logs(from_block, to_block)

        events: list[tuple[int, int, str, EventData]] = []
        events += [(log['blockNumber'], log['logIndex'], 'add', log) for log in added]
        events += [(log['blockNumber'], log['logIndex'], 'exec', log) for log in executed]
        events += [(log['blockNumber'], log['logIndex'], 'remove', log) for log in removed]
        events.sort(key=lambda e: (e[0], e[1]))  # (blockNumber, logIndex) order is critical

        for _bn, _li, kind, log in events:
            if kind == 'add':
                batch_hash, pubkeys = self._decode_added(log)
                self.store.add_batch(batch_hash, pubkeys)
            elif kind == 'exec':
                self.store.close_batch(_to_hex(log['args']['batchHash']))
            else:  # remove
                for h in log['args']['batchHashes']:
                    self.store.close_batch(_to_hex(h))

    # ---- tail (ephemeral, finalized -> latest, ADD-only) ----
    def get_filter_set(self, tail_from: int, tail_to: int) -> set[bytes]:
        """Pending pubkeys for the top-up filter: base ∪ ephemeral ADD-only tail."""
        pending = self.store.pending_pubkeys()
        pending |= self._read_tail_added(tail_from, tail_to)
        return pending

    def _read_tail_added(self, from_block: int, to_block: int) -> set[bytes]:
        result: set[bytes] = set()
        if from_block > to_block:
            return result
        frm = from_block
        while frm <= to_block:
            to = min(frm + self.chunk - 1, to_block)
            for log in self.contract.get_requests_added_logs(frm, to):
                _batch_hash, pubkeys = self._decode_added(log)
                result.update(pubkeys)
            frm = to + 1
        return result

    # ---- helpers ----
    def _decode_added(self, log: EventData) -> tuple[str, list[bytes]]:
        data = bytes(log['args']['batchData'])
        batch_hash = _to_hex(self.w3.keccak(data))
        groups = abi_decode(_BATCH_DATA_ABI, data)[0]
        pubkeys: list[bytes] = []
        for source_pubkeys, target_pubkey in groups:
            pubkeys.extend(bytes(p) for p in source_pubkeys)
            pubkeys.append(bytes(target_pubkey))
        return batch_hash, pubkeys

    def _finalized_block(self) -> int:
        return self.w3.eth.get_block('finalized')['number']
