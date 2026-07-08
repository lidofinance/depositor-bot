"""Integration test for ConsolidationIndexer against a real ConsolidationBus (Hoodi).

Read-only: connects directly to the EL RPC (no anvil fork needed) and replays the live
contract history. Skips unless an RPC for a chain with a configured ConsolidationBus is set
in WEB3_RPC_ENDPOINTS (or TESTNET_WEB3_RPC_ENDPOINTS).

Run: poetry run pytest tests/blockchain/consolidation/test_indexer_integration.py -m integration -s
"""

import time
from typing import cast

import pytest
import variables
from blockchain.consolidation.indexer import ConsolidationIndexer
from blockchain.consolidation.store import InMemoryPendingStore
from blockchain.contracts.consolidation_bus import ConsolidationBusContract
from web3 import HTTPProvider, Web3

_ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'


@pytest.fixture
def consolidation_indexer_live():
    w3 = Web3(HTTPProvider(variables.WEB3_RPC_ENDPOINTS[0], request_kwargs={'timeout': 600}))
    assert w3.is_connected(), 'Failed to connect to the Web3 provider.'

    chain_id = w3.eth.chain_id
    address, deploy_block = variables.get_consolidation_bus_config(chain_id)
    assert address is not None and deploy_block is not None, f'ConsolidationBus not configured for chain {chain_id}.'

    contract = cast(
        ConsolidationBusContract,
        w3.eth.contract(address=address, ContractFactoryClass=ConsolidationBusContract),
    )
    store = InMemoryPendingStore()
    indexer = ConsolidationIndexer(w3, contract, store, deploy_block, variables.CONSOLIDATION_GETLOGS_CHUNK)
    return w3, contract, store, indexer


@pytest.mark.integration
def test_cold_start_against_live_consolidation_bus(consolidation_indexer_live):
    w3, contract, store, indexer = consolidation_indexer_live

    # 1. Cold start replays the whole on-chain history without error.
    t0 = time.monotonic()
    indexer.cold_start()
    cold_dt = time.monotonic() - t0
    print(f'\ncold_start: {cold_dt:.1f}s | pending_batches={store.pending_batch_count()} pending_pubkeys={store.pending_pubkey_count()}')
    # cold_start raises on failure (fatal), so reaching here means it succeeded.

    # 2. Correctness cross-check: every batch we hold as pending is actually open on-chain.
    #    getBatchInfo(batchHash).publisher == 0x0 would mean it is NOT pending.
    for batch_hash in list(store._batches.keys()):
        publisher, _added_at = contract.get_batch_info(bytes.fromhex(batch_hash))
        assert publisher != _ZERO_ADDRESS, f'batch {batch_hash} is not pending on-chain'

    # 3. Every pending pubkey decoded to a valid 48-byte BLS pubkey.
    for pk in store.pending_pubkeys():
        assert len(pk) == 48

    # 4. Tail read works and is a superset of the base pending set (ADD-only union).
    finalized = indexer._finalized_block()
    base = store.pending_pubkeys()
    t1 = time.monotonic()
    filter_set = indexer.get_filter_set(finalized + 1, w3.eth.block_number)
    tail_dt = time.monotonic() - t1
    print(f'tail read: {tail_dt:.1f}s | filter_set={len(filter_set)}')
    assert base <= filter_set
