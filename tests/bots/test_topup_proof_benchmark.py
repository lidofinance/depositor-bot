"""
Benchmark: measure top-up proof building time for N validators on mainnet.

Uses module 3 (CSM), real EL/CL/Keys API endpoints.

Run:
    BENCH_TOPUP=1 \
    WEB3_RPC_ENDPOINTS=https://... \
    CL_API_URLS=https://... \
    KEYS_API_URL=https://... \
    poetry run pytest tests/bots/test_topup_proof_benchmark.py -v -s

Results are written to tests/bots/topup_bench_results.json
"""

import json
import os
import time

import pytest
import variables
from blockchain.beacon_state.state import load_beacon_state_data
from blockchain.topup.cmv2_strategy import _check_key_eligibility
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.types import TopUpCandidate
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient
from web3 import HTTPProvider, Web3

MODULE_ID = 3
CANDIDATE_COUNTS = [10, 25, 50, 75, 100]


@pytest.fixture(autouse=True)
def bench_only():
    if not os.getenv('BENCH_TOPUP'):
        pytest.skip('Set BENCH_TOPUP=1 to run this benchmark.')


@pytest.fixture(scope='module')
def w3() -> Web3:
    endpoint = variables.WEB3_RPC_ENDPOINTS[0]
    return Web3(HTTPProvider(endpoint, request_kwargs={'timeout': 60}))


@pytest.fixture(scope='module')
def keys_api() -> KeysAPIClient:
    if not variables.KEYS_API_URL:
        pytest.skip('KEYS_API_URL is not configured.')
    return KeysAPIClient(
        host=variables.KEYS_API_URL,
        request_timeout=60,
        retry_total=3,
        retry_backoff_factor=2,
    )


@pytest.fixture(scope='module')
def cl() -> ConsensusClient:
    if not variables.CL_API_URLS:
        pytest.skip('CL_API_URLS is not configured.')
    return ConsensusClient(
        hosts=variables.CL_API_URLS,
        request_timeout=variables.HTTP_REQUEST_TIMEOUT_CONSENSUS,
        retry_total=3,
        retry_backoff_factor=2,
    )


@pytest.fixture(scope='module')
def module_keys(keys_api: KeysAPIClient):
    t0 = time.monotonic()
    keys = keys_api.get_module_used_keys(MODULE_ID)
    elapsed = time.monotonic() - t0
    print(f'\n[keys_api] fetched {len(keys)} keys in {elapsed:.2f}s')
    return keys


@pytest.fixture(scope='module')
def beacon_data_and_timing(w3: Web3, cl: ConsensusClient, module_keys):
    pubkeys = set()
    for k in module_keys:
        raw = k.key
        if raw.startswith('0x'):
            raw = raw[2:]
        pubkeys.add(bytes.fromhex(raw))

    t0 = time.monotonic()
    beacon_data = load_beacon_state_data(w3, cl, pubkeys)
    elapsed = time.monotonic() - t0
    print(f'\n[load_beacon_state_data] {elapsed:.2f}s for {len(pubkeys)} pubkeys')
    return beacon_data, elapsed


@pytest.fixture(scope='module')
def eligible_candidates(module_keys, beacon_data_and_timing) -> list[TopUpCandidate]:
    beacon_data = beacon_data_and_timing[0]
    candidates = []
    for key in module_keys:
        candidate = _check_key_eligibility(key, beacon_data)
        if candidate is not None:
            candidates.append(candidate)
    candidates.sort(key=lambda c: c.key_index)
    print(f'\n[eligibility] {len(candidates)} eligible out of {len(module_keys)} keys')
    return candidates


@pytest.mark.integration
def test_topup_proof_benchmark(
    beacon_data_and_timing,
    eligible_candidates: list[TopUpCandidate],
):
    beacon_data, load_time = beacon_data_and_timing

    if not eligible_candidates:
        pytest.skip('No eligible candidates found in module 3.')

    results = {
        'module_id': MODULE_ID,
        'total_keys': len(eligible_candidates),
        'load_beacon_state_seconds': round(load_time, 2),
        'slot': beacon_data.slot,
        'runs': [],
    }

    for n in CANDIDATE_COUNTS:
        if n > len(eligible_candidates):
            print(f'\n[skip] only {len(eligible_candidates)} eligible candidates, cannot test n={n}')
            break

        subset = eligible_candidates[:n]

        t0 = time.monotonic()
        _proof_data = build_topup_proofs(beacon_data, subset)
        elapsed = time.monotonic() - t0

        run = {
            'candidates': n,
            'build_proofs_seconds': round(elapsed, 2),
            'per_candidate_seconds': round(elapsed / n, 4),
        }
        results['runs'].append(run)
        print(f'\n[build_topup_proofs] n={n:>3}: {elapsed:.2f}s total, {elapsed / n:.4f}s per candidate')

    out_path = os.path.join(os.path.dirname(__file__), 'topup_bench_results.json')
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'\nResults saved to {out_path}')
    assert results['runs'], 'No benchmark runs completed'
