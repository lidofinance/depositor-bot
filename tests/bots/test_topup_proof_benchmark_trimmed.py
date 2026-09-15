"""Trimmed top-up proof benchmark: real code path, no module / Keys API / eligibility.

Measures exactly what we care about — pulling the SSZ state, decoding it, and building proofs —
using the production functions (load_raw_beacon_state -> extract_state_data -> build_topup_proofs).
Candidates are just N validators taken straight from the decoded state (their index is all the
proof needs), so it runs on any network without hunting for eligible module keys.

Needs only an EL and a CL endpoint (no Keys API):
    BENCH_TOPUP=1 \
    WEB3_RPC_ENDPOINTS=https://... \
    CL_API_URLS=https://... \
    poetry run pytest tests/bots/test_topup_proof_benchmark_trimmed.py -v -s

Results are written to tests/bots/topup_bench_results_trimmed.json
"""

import json
import os
import time

import pytest
from web3 import HTTPProvider, Web3

import variables
from blockchain.beacon_state.state import extract_state_data, load_raw_beacon_state
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.types import TopUpCandidate
from providers.consensus import ConsensusClient

CANDIDATE_COUNTS = [10, 25, 50, 100]


@pytest.fixture(autouse=True)
def bench_only():
    if not os.getenv('BENCH_TOPUP'):
        pytest.skip('Set BENCH_TOPUP=1 to run this benchmark.')


@pytest.fixture(scope='module')
def w3() -> Web3:
    if not variables.WEB3_RPC_ENDPOINTS:
        pytest.skip('WEB3_RPC_ENDPOINTS is not configured.')
    return Web3(HTTPProvider(variables.WEB3_RPC_ENDPOINTS[0], request_kwargs={'timeout': 60}))


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
def loaded(w3: Web3, cl: ConsensusClient):
    # The metric that matters: SSZ fetch + decode + root self-check + pubkey map, via the real path.
    t0 = time.monotonic()
    raw = load_raw_beacon_state(w3, cl)
    load_time = time.monotonic() - t0
    n = len(raw.raw_state.validators)
    print(f'\n[load_raw_beacon_state] {load_time:.2f}s  (slot={raw.slot}, validators={n})')
    return raw, load_time


@pytest.mark.integration
def test_trimmed_proof_benchmark(loaded):
    raw, load_time = loaded
    total = len(raw.raw_state.validators)
    count = min(max(CANDIDATE_COUNTS), total)
    if count == 0:
        pytest.skip('State has no validators.')

    # N validator indices spread across the whole list (proof time is index-dependent only).
    step = max((total - 1) // max(count - 1, 1), 1)
    indices = [min(i * step, total - 1) for i in range(count)]
    pubkeys = {bytes(raw.raw_state.validators[i].pubkey) for i in indices}

    # Real extract path fills validators_fields / pubkey_to_index for exactly these validators.
    beacon_data = extract_state_data(raw, pubkeys)

    # Candidates straight from the state; key_index/operator_id/pending don't affect proof time.
    candidates = [
        TopUpCandidate(
            validator_index=i,
            key_index=0,
            operator_id=0,
            pubkey=beacon_data.validators_fields[i].pubkey,
            pending_balance=0,
        )
        for i in indices
    ]

    results = {
        'network_slot': beacon_data.slot,
        'validators': total,
        'load_beacon_state_seconds': round(load_time, 2),
        'runs': [],
    }

    for n in CANDIDATE_COUNTS:
        if n > len(candidates):
            print(f'\n[skip] only {len(candidates)} validators available, cannot test n={n}')
            break
        subset = candidates[:n]

        t0 = time.monotonic()
        build_topup_proofs(beacon_data, subset)  # builds + verifies each proof
        elapsed = time.monotonic() - t0

        results['runs'].append(
            {
                'candidates': n,
                'build_proofs_seconds': round(elapsed, 2),
                'per_candidate_seconds': round(elapsed / n, 4),
            }
        )
        print(f'\n[build_topup_proofs] n={n:>3}: {elapsed:.2f}s total, {elapsed / n:.4f}s per candidate')

    out_path = os.path.join(os.path.dirname(__file__), 'topup_bench_results_trimmed.json')
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'\nResults saved to {out_path}')
    assert results['runs'], 'No benchmark runs completed'
