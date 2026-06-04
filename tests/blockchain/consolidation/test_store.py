"""Isolated unit tests for InMemoryPendingStore.

No RPC, no mocks, no disk — pure in-memory store.
"""

import pytest
from blockchain.consolidation.store import InMemoryPendingStore


# ---- helpers ----
def _pk(b: int) -> bytes:
    """A valid 48-byte pubkey filled with byte `b`."""
    return bytes([b]) * 48


def _hash(s: str) -> str:
    """A 64-hex-char batchHash from a short seed string."""
    return (s * 64)[:64]


@pytest.fixture
def store():
    s = InMemoryPendingStore()
    yield s
    s.close()


# ---- 1. add + is_pending ----
@pytest.mark.unit
def test_add_batch_marks_pubkeys_pending(store):
    """add_batch -> is_pending True for its pubkeys, False for others."""
    store.add_batch(_hash('a'), [_pk(1), _pk(2)])

    assert store.is_pending(_pk(1))
    assert store.is_pending(_pk(2))
    assert not store.is_pending(_pk(9))


# ---- 2. pending_pubkeys ----
@pytest.mark.unit
def test_pending_pubkeys_returns_added_set(store):
    """pending_pubkeys returns exactly the added pubkeys as bytes (hex round-trip)."""
    store.add_batch(_hash('a'), [_pk(1), _pk(2)])

    assert store.pending_pubkeys() == {_pk(1), _pk(2)}


# ---- 3. close removes ----
@pytest.mark.unit
def test_close_batch_removes_pubkeys(store):
    """After close_batch: is_pending False, pending_pubkeys empty, counts 0."""
    h = _hash('a')
    store.add_batch(h, [_pk(1), _pk(2)])

    store.close_batch(h)

    assert not store.is_pending(_pk(1))
    assert not store.is_pending(_pk(2))
    assert store.pending_pubkeys() == set()
    assert store.pending_batch_count() == 0
    assert store.pending_pubkey_count() == 0


# ---- 4. close idempotent ----
@pytest.mark.unit
def test_close_batch_is_idempotent(store):
    """close_batch of an unknown hash is a no-op; double close is a no-op."""
    h = _hash('a')
    store.add_batch(h, [_pk(1)])

    # closing an unknown hash must not raise and must not touch existing state
    store.close_batch(_hash('z'))
    assert store.pending_batch_count() == 1
    assert store.pending_pubkey_count() == 1

    store.close_batch(h)
    assert not store.is_pending(_pk(1))
    assert store.pending_batch_count() == 0
    assert store.pending_pubkey_count() == 0

    # double close -> still a no-op, counts unchanged
    store.close_batch(h)
    assert store.pending_batch_count() == 0
    assert store.pending_pubkey_count() == 0


# ---- 5. shared pubkey across batches ----
@pytest.mark.unit
def test_shared_pubkey_stays_pending_until_all_batches_closed(store):
    """A pubkey in two batches stays pending until both are closed (separate pk: records)."""
    a, b = _hash('a'), _hash('b')
    store.add_batch(a, [_pk(1)])
    store.add_batch(b, [_pk(1)])

    assert store.is_pending(_pk(1))

    store.close_batch(a)
    assert store.is_pending(_pk(1))  # still referenced by batch b

    store.close_batch(b)
    assert not store.is_pending(_pk(1))


# ---- 6. cursor ----
@pytest.mark.unit
def test_cursor_default_then_set(store):
    """get_cursor returns default when unset, then the set value."""
    assert store.get_cursor(default=5) == 5

    store.set_cursor(100)
    assert store.get_cursor(default=5) == 100


# ---- 7. counts ----
@pytest.mark.unit
def test_counts_track_adds_and_closes(store):
    """pending_batch_count / pending_pubkey_count are correct across add/close."""
    a, b = _hash('a'), _hash('b')
    store.add_batch(a, [_pk(1), _pk(2)])
    store.add_batch(b, [_pk(3)])

    assert store.pending_batch_count() == 2
    assert store.pending_pubkey_count() == 3

    store.close_batch(a)
    assert store.pending_batch_count() == 1
    assert store.pending_pubkey_count() == 1


# ---- 8. wipe ----
@pytest.mark.unit
def test_wipe_clears_everything(store):
    """After wipe: empty pending, counts 0, cursor back to default."""
    store.add_batch(_hash('a'), [_pk(1)])
    store.set_cursor(10)

    store.wipe()

    assert not store.is_pending(_pk(1))
    assert store.pending_batch_count() == 0
    assert store.pending_pubkey_count() == 0
    assert store.get_cursor(default=7) == 7


# ---- 9. approx memory ----
@pytest.mark.unit
def test_approx_memory_bytes_grows_with_data(store):
    """approx_memory_bytes is 0 when empty and > 0 once data is written."""
    assert store.approx_memory_bytes() == 0

    store.add_batch(_hash('a'), [_pk(1)])
    assert store.approx_memory_bytes() > 0


# ---- 10. edge: empty batch ----
@pytest.mark.unit
def test_add_empty_batch_creates_only_batch_record(store):
    """add_batch with no pubkeys: 1 batch record, 0 pk records."""
    store.add_batch(_hash('a'), [])

    assert store.pending_batch_count() == 1
    assert store.pending_pubkey_count() == 0


# ---- 11. add_batch idempotency (fix A) ----
@pytest.mark.unit
def test_add_same_batch_twice_is_idempotent(store):
    """Re-adding the same batch must not double-count: one close fully clears it (no phantom)."""
    h = _hash('a')
    store.add_batch(h, [_pk(1), _pk(2)])
    store.add_batch(h, [_pk(1), _pk(2)])  # duplicate add (e.g. overlapping range / replay)

    assert store.pending_batch_count() == 1
    assert store.pending_pubkey_count() == 2

    store.close_batch(h)
    assert not store.is_pending(_pk(1))
    assert not store.is_pending(_pk(2))
    assert store.pending_pubkey_count() == 0


# ---- 12. dedup within a batch (fix C) ----
@pytest.mark.unit
def test_duplicate_pubkeys_within_batch_counted_once(store):
    """A pubkey listed twice in one batch yields a single record; close clears it."""
    h = _hash('a')
    store.add_batch(h, [_pk(1), _pk(1), _pk(2)])

    assert store.pending_pubkey_count() == 2  # _pk(1) de-duped
    assert store.pending_pubkeys() == {_pk(1), _pk(2)}

    store.close_batch(h)
    assert not store.is_pending(_pk(1))
    assert store.pending_pubkey_count() == 0


# ---- 13. shared pubkey: record count vs distinct ----
@pytest.mark.unit
def test_shared_pubkey_counts_records_and_distinct(store):
    """pending_pubkey_count counts (pubkey, batch) records; pending_pubkeys is the distinct set."""
    a, b = _hash('a'), _hash('b')
    store.add_batch(a, [_pk(1)])
    store.add_batch(b, [_pk(1)])

    assert store.pending_pubkey_count() == 2  # two records
    assert store.pending_pubkeys() == {_pk(1)}  # one distinct pubkey


# ---- 14. cursor overwrite ----
@pytest.mark.unit
def test_set_cursor_overwrites(store):
    """set_cursor keeps the latest value."""
    store.set_cursor(10)
    store.set_cursor(20)

    assert store.get_cursor(default=0) == 20


# ---- 15. pending_pubkeys returns an independent copy ----
@pytest.mark.unit
def test_pending_pubkeys_is_a_copy(store):
    """Mutating the returned set must not corrupt the store's internal state."""
    store.add_batch(_hash('a'), [_pk(1)])

    snapshot = store.pending_pubkeys()
    snapshot.add(_pk(9))
    snapshot.discard(_pk(1))

    assert store.is_pending(_pk(1))
    assert not store.is_pending(_pk(9))


# ---- 16. close empty batch ----
@pytest.mark.unit
def test_close_empty_batch_is_noop(store):
    """Closing a batch that had no pubkeys removes its record without error."""
    h = _hash('a')
    store.add_batch(h, [])

    store.close_batch(h)

    assert store.pending_batch_count() == 0


# ---- 17. close removes exactly the target batch, leaves others intact ----
@pytest.mark.unit
def test_close_removes_only_target_batch(store):
    """Closing one batch drops its record + its pubkeys; an unrelated batch stays untouched."""
    a, b = _hash('a'), _hash('b')
    store.add_batch(a, [_pk(1), _pk(2)])
    store.add_batch(b, [_pk(3)])

    store.close_batch(a)

    # batch a (record + pubkeys) gone
    assert not store.is_pending(_pk(1))
    assert not store.is_pending(_pk(2))
    # batch b fully intact
    assert store.is_pending(_pk(3))
    assert store.pending_batch_count() == 1
    assert store.pending_pubkeys() == {_pk(3)}
