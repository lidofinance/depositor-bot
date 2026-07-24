"""In-memory store for the pending ConsolidationBus set.

Structures:
    _batches: dict[batchHash -> tuple(pubkeys)]       # reverse map, for close-by-hash
    _pending: Counter[pubkey -> live-batch refcount]  # membership; a pubkey shared across
                                                       # batches stays pending until all close
"""

import logging
from collections import Counter

logger = logging.getLogger(__name__)


class InMemoryPendingStore:
    def __init__(self):
        self._batches: dict[str, tuple[bytes, ...]] = {}
        self._pending: Counter[bytes] = Counter()
        self._cursor: int | None = None

    def wipe(self) -> None:
        self._batches.clear()
        self._pending.clear()
        self._cursor = None

    # ---- write ----
    def add_batch(self, batch_hash: str, pubkeys: list[bytes]) -> None:
        if batch_hash in self._batches:
            return  # (A) idempotent: re-adding the same batch must not double-count
        keys = tuple(dict.fromkeys(pubkeys))  # (C) de-dup within the batch, keep order
        self._batches[batch_hash] = keys
        self._pending.update(keys)

    def close_batch(self, batch_hash: str) -> None:
        keys = self._batches.pop(batch_hash, None)
        if keys is None:
            return  # idempotent: unknown / already closed
        for pk in keys:
            if self._pending.get(pk, 0) <= 1:
                self._pending.pop(pk, None)  # (B) drop zero-count entries
            else:
                self._pending[pk] -= 1

    # ---- read ----
    def is_pending(self, pubkey: bytes) -> bool:
        return pubkey in self._pending

    def pending_pubkeys(self) -> set[bytes]:
        return set(self._pending)

    # ---- metrics ----
    def pending_batch_count(self) -> int:
        return len(self._batches)

    def pending_pubkey_count(self) -> int:
        return sum(self._pending.values())

    # ---- cursor ----
    def get_cursor(self, default: int) -> int:
        return self._cursor if self._cursor is not None else default

    def set_cursor(self, block: int) -> None:
        self._cursor = block
