"""Isolated unit tests for ConsolidationIndexer.

No RPC: a fake ConsolidationBus contract returns canned logs; w3.keccak is the real one
(so batchHash matches), w3.eth.get_block('finalized') is stubbed. The store is the real
InMemoryPendingStore, so these also exercise the indexer↔store integration.
"""

from unittest.mock import Mock

import pytest
from blockchain.consolidation.indexer import ConsolidationIndexer
from blockchain.consolidation.store import InMemoryPendingStore
from eth_abi.abi import encode
from web3 import Web3


# ---- helpers ----
def _pk(b: int) -> bytes:
    return bytes([b]) * 48


def _batch(groups: list[tuple[list[bytes], bytes]]) -> tuple[bytes, str, list[bytes]]:
    """Build (batchData, batchHash_hex, pubkeys) for a list of (sourcePubkeys, targetPubkey) groups."""
    data = encode(['(bytes[],bytes)[]'], [groups])
    batch_hash = bytes(Web3.keccak(data)).hex()
    pubkeys: list[bytes] = []
    for sources, target in groups:
        pubkeys.extend(sources)
        pubkeys.append(target)
    return data, batch_hash, pubkeys


class FakeBus:
    """Stand-in for ConsolidationBusContract: stores logs, serves them by block range."""

    def __init__(self):
        self._added: list[dict] = []
        self._executed: list[dict] = []
        self._removed: list[dict] = []
        self.added_ranges: list[tuple[int, int]] = []  # records get_requests_added_logs(from, to)

    def add_added(self, block: int, log_index: int, batch_data: bytes) -> None:
        self._added.append({'blockNumber': block, 'logIndex': log_index, 'args': {'batchData': batch_data, 'publisher': '0xpub'}})

    def add_executed(self, block: int, log_index: int, batch_hash_hex: str) -> None:
        self._executed.append({'blockNumber': block, 'logIndex': log_index, 'args': {'batchHash': bytes.fromhex(batch_hash_hex)}})

    def add_removed(self, block: int, log_index: int, batch_hash_hexes: list[str]) -> None:
        hashes = [bytes.fromhex(h) for h in batch_hash_hexes]
        self._removed.append({'blockNumber': block, 'logIndex': log_index, 'args': {'batchHashes': hashes}})

    @staticmethod
    def _in_range(logs, from_block, to_block):
        return [log for log in logs if from_block <= log['blockNumber'] <= to_block]

    def get_requests_added_logs(self, from_block, to_block):
        self.added_ranges.append((from_block, to_block))
        return self._in_range(self._added, from_block, to_block)

    def get_requests_executed_logs(self, from_block, to_block):
        return self._in_range(self._executed, from_block, to_block)

    def get_batches_removed_logs(self, from_block, to_block):
        return self._in_range(self._removed, from_block, to_block)


def _make_w3(finalized: int) -> Mock:
    w3 = Mock()
    w3.keccak = Web3.keccak  # real keccak so batchHash matches the contract
    w3.eth.get_block.return_value = {'number': finalized}
    return w3


def _make_indexer(finalized: int, deploy_block: int = 0, chunk: int = 10_000) -> tuple[ConsolidationIndexer, FakeBus, InMemoryPendingStore]:
    bus = FakeBus()
    store = InMemoryPendingStore()
    indexer = ConsolidationIndexer(_make_w3(finalized), bus, store, deploy_block=deploy_block, chunk=chunk)
    return indexer, bus, store


# ---- 1. decode ----
@pytest.mark.unit
def test_decode_added_extracts_source_and_target_pubkeys():
    data, batch_hash, pubkeys = _batch([([_pk(1), _pk(2)], _pk(3)), ([_pk(4)], _pk(5))])
    indexer, _bus, _store = _make_indexer(finalized=0)

    log = {'args': {'batchData': data}, 'blockNumber': 1, 'logIndex': 0}
    decoded_hash, decoded_pubkeys = indexer._decode_added(log)

    assert decoded_hash == batch_hash
    assert decoded_pubkeys == [_pk(1), _pk(2), _pk(3), _pk(4), _pk(5)]


# ---- 2. add -> pending ----
@pytest.mark.unit
def test_sync_indexes_added_batch():
    data, batch_hash, pubkeys = _batch([([_pk(1)], _pk(2))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_added(block=5, log_index=0, batch_data=data)

    indexer.sync_base_to_finalized()

    assert store.is_pending(_pk(1))
    assert store.is_pending(_pk(2))
    assert store.pending_batch_count() == 1
    assert store.get_cursor(default=-1) == 10  # cursor advanced to finalized


# ---- 3. replay order: add then exec in same block ----
@pytest.mark.unit
def test_add_then_exec_same_block_closes_batch():
    data, batch_hash, _ = _batch([([_pk(1)], _pk(2))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_added(block=5, log_index=0, batch_data=data)
    bus.add_executed(block=5, log_index=1, batch_hash_hex=batch_hash)  # later logIndex -> applied after add

    indexer.sync_base_to_finalized()

    assert not store.is_pending(_pk(1))
    assert store.pending_batch_count() == 0


# ---- 4. replay order: exec before add (lower logIndex) is a no-op ----
@pytest.mark.unit
def test_exec_before_add_is_noop_keeps_pending():
    data, batch_hash, _ = _batch([([_pk(1)], _pk(2))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_executed(block=5, log_index=0, batch_hash_hex=batch_hash)  # earlier -> batch not yet known
    bus.add_added(block=5, log_index=1, batch_data=data)

    indexer.sync_base_to_finalized()

    assert store.is_pending(_pk(1))
    assert store.pending_batch_count() == 1


# ---- 5. BatchesRemoved closes ----
@pytest.mark.unit
def test_batches_removed_closes_batch():
    data, batch_hash, _ = _batch([([_pk(1)], _pk(2))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_added(block=3, log_index=0, batch_data=data)
    bus.add_removed(block=7, log_index=0, batch_hash_hexes=[batch_hash])

    indexer.sync_base_to_finalized()

    assert not store.is_pending(_pk(1))
    assert store.pending_batch_count() == 0


# ---- 6. chunking applies events across chunks ----
@pytest.mark.unit
def test_chunked_sync_applies_all_events():
    d1, _h1, _ = _batch([([_pk(1)], _pk(2))])
    d2, _h2, _ = _batch([([_pk(3)], _pk(4))])
    indexer, bus, store = _make_indexer(finalized=5, chunk=2)  # ranges: [0,1],[2,3],[4,5]
    bus.add_added(block=0, log_index=0, batch_data=d1)
    bus.add_added(block=4, log_index=0, batch_data=d2)

    indexer.sync_base_to_finalized()

    assert store.is_pending(_pk(1))
    assert store.is_pending(_pk(3))
    assert bus.added_ranges == [(0, 1), (2, 3), (4, 5)]
    assert store.get_cursor(default=-1) == 5


# ---- 7. incremental resume from cursor ----
@pytest.mark.unit
def test_resume_reads_only_new_blocks():
    d1, _h1, _ = _batch([([_pk(1)], _pk(2))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_added(block=5, log_index=0, batch_data=d1)
    indexer.sync_base_to_finalized()  # cursor -> 10

    # finalized moves forward; a second sync must start at cursor+1
    bus.added_ranges.clear()
    indexer.w3.eth.get_block.return_value = {'number': 20}
    d2, _h2, _ = _batch([([_pk(3)], _pk(4))])
    bus.add_added(block=15, log_index=0, batch_data=d2)

    indexer.sync_base_to_finalized()

    assert bus.added_ranges == [(11, 20)]  # did not re-read 0..10
    assert store.is_pending(_pk(3))


# ---- 8. nothing to do when finalized <= cursor ----
@pytest.mark.unit
def test_sync_noop_when_finalized_not_advanced():
    indexer, bus, store = _make_indexer(finalized=10)
    indexer.sync_base_to_finalized()
    bus.added_ranges.clear()

    indexer.sync_base_to_finalized()  # same finalized

    assert bus.added_ranges == []  # start (11) > finalized (10) -> no read


# ---- 9. get_filter_set = base ∪ ADD-only tail ----
@pytest.mark.unit
def test_get_filter_set_unions_base_and_tail():
    base_data, _bh, _ = _batch([([_pk(1)], _pk(2))])
    tail_data, _th, _ = _batch([([_pk(3)], _pk(4))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_added(block=5, log_index=0, batch_data=base_data)  # base
    indexer.sync_base_to_finalized()

    bus.add_added(block=15, log_index=0, batch_data=tail_data)  # tail (finalized+1..latest)

    result = indexer.get_filter_set(tail_from=11, tail_to=20)

    assert result == {_pk(1), _pk(2), _pk(3), _pk(4)}


# ---- 10. tail is ADD-only: a close inside the tail is ignored ----
@pytest.mark.unit
def test_tail_ignores_close_events():
    tail_data, tail_hash, _ = _batch([([_pk(3)], _pk(4))])
    indexer, bus, _store = _make_indexer(finalized=10)
    indexer.sync_base_to_finalized()

    # In the tail window the batch is added AND executed — ADD-only means it stays excluded.
    bus.add_added(block=15, log_index=0, batch_data=tail_data)
    bus.add_executed(block=16, log_index=0, batch_hash_hex=tail_hash)

    result = indexer.get_filter_set(tail_from=11, tail_to=20)

    assert result == {_pk(3), _pk(4)}


# ---- 11. empty tail range ----
@pytest.mark.unit
def test_get_filter_set_empty_tail_returns_base_only():
    base_data, _bh, _ = _batch([([_pk(1)], _pk(2))])
    indexer, bus, _store = _make_indexer(finalized=10)
    bus.add_added(block=5, log_index=0, batch_data=base_data)
    indexer.sync_base_to_finalized()

    # tail_from > tail_to -> no tail read
    result = indexer.get_filter_set(tail_from=11, tail_to=10)

    assert result == {_pk(1), _pk(2)}


# ---- 11b. is_ready is False before cold_start ----
@pytest.mark.unit
def test_is_ready_false_before_cold_start():
    """A freshly built indexer is not ready until cold_start succeeds (bot guard relies on this)."""
    indexer, _bus, _store = _make_indexer(finalized=10)

    assert indexer.is_ready is False


# ---- 12. cold_start success ----
@pytest.mark.unit
def test_cold_start_sets_ready():
    data, _bh, _ = _batch([([_pk(1)], _pk(2))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_added(block=5, log_index=0, batch_data=data)

    indexer.cold_start()

    assert indexer.is_ready is True
    assert store.is_pending(_pk(1))


# ---- 13. cold_start failure -> not ready ----
@pytest.mark.unit
def test_cold_start_failure_marks_not_ready():
    indexer, bus, _store = _make_indexer(finalized=10)
    indexer.w3.eth.get_block.side_effect = Exception('rpc down')

    indexer.cold_start()

    assert indexer.is_ready is False


# ---- 14. BatchesRemoved with multiple hashes closes all ----
@pytest.mark.unit
def test_batches_removed_multiple_hashes_closes_all():
    d1, h1, _ = _batch([([_pk(1)], _pk(2))])
    d2, h2, _ = _batch([([_pk(3)], _pk(4))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_added(block=1, log_index=0, batch_data=d1)
    bus.add_added(block=2, log_index=0, batch_data=d2)
    bus.add_removed(block=5, log_index=0, batch_hash_hexes=[h1, h2])

    indexer.sync_base_to_finalized()

    assert store.pending_batch_count() == 0
    assert not store.is_pending(_pk(1))
    assert not store.is_pending(_pk(3))


# ---- 15. deploy_block is respected (no reads before it) ----
@pytest.mark.unit
def test_cold_start_begins_at_deploy_block():
    indexer, bus, _store = _make_indexer(finalized=110, deploy_block=100)

    indexer.sync_base_to_finalized()

    assert bus.added_ranges == [(100, 110)]  # never reads blocks before deploy_block


# ---- 16. tail read is chunked ----
@pytest.mark.unit
def test_tail_read_is_chunked():
    indexer, bus, _store = _make_indexer(finalized=10, chunk=2)
    indexer.sync_base_to_finalized()
    bus.added_ranges.clear()

    tail_data, _th, _ = _batch([([_pk(3)], _pk(4))])
    bus.add_added(block=13, log_index=0, batch_data=tail_data)

    result = indexer.get_filter_set(tail_from=11, tail_to=16)

    assert result == {_pk(3), _pk(4)}
    assert bus.added_ranges == [(11, 12), (13, 14), (15, 16)]


# ---- 17. close across chunk boundary ----
@pytest.mark.unit
def test_close_across_chunk_boundary():
    data, batch_hash, _ = _batch([([_pk(1)], _pk(2))])
    indexer, bus, store = _make_indexer(finalized=10, chunk=2)  # add in [0,1], exec in [4,5]
    bus.add_added(block=1, log_index=0, batch_data=data)
    bus.add_executed(block=5, log_index=0, batch_hash_hex=batch_hash)

    indexer.sync_base_to_finalized()

    assert not store.is_pending(_pk(1))
    assert store.pending_batch_count() == 0


# ---- 18. sequence collapses to the current pending set ----
@pytest.mark.unit
def test_sequence_collapses_to_pending_set():
    da, ha, _ = _batch([([_pk(1)], _pk(2))])
    db, _hb, _ = _batch([([_pk(3)], _pk(4))])
    indexer, bus, store = _make_indexer(finalized=10)
    bus.add_added(block=1, log_index=0, batch_data=da)  # A
    bus.add_added(block=2, log_index=0, batch_data=db)  # B
    bus.add_executed(block=3, log_index=0, batch_hash_hex=ha)  # close A

    indexer.sync_base_to_finalized()

    assert store.pending_pubkeys() == {_pk(3), _pk(4)}  # only B remains
    assert store.pending_batch_count() == 1
