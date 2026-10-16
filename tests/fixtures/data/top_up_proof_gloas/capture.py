"""Capture an offline Gloas top-up snapshot from a live devnet.

Writes everything test_gloas_topup_replay needs to replay TopUpGateway.topUp without the devnet:
the Gloas beacon state (SSZ), the anchor header / EL block, the candidates, the proofs the contract
accepted, and the prestate (code + touched storage) of every account topUp reads at the anchor block.

The topUp call is simulated on the devnet first; nothing is written unless the contract accepts it.

    GLOAS_PIVOT_SLOT=<GLOAS_FORK_EPOCH * 32> CAPTURE_EL=... CAPTURE_CL=... CAPTURE_KAPI=... CAPTURE_LOCATOR=0x... CAPTURE_MODULE_ID=4 \
    PYTHONPATH=src poetry run python tests/fixtures/data/top_up_proof_gloas/capture.py

Needs an EL with debug_traceCall (prestateTracer) and a CL that serves the head state.
"""

import json
import os
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from web3 import HTTPProvider, Web3

from blockchain.beacon_state.constants import FAR_FUTURE_EPOCH, GLOAS_PIVOT_SLOT, SLOTS_PER_EPOCH
from blockchain.beacon_state.specs import get_spec
from blockchain.beacon_state.state import extract_state_data, load_raw_beacon_state
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.topup_gateway import TopUpGatewayContract
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.types import TopUpCandidate
from providers.consensus import ConsensusClient

OUT_DIR = Path(__file__).resolve().parent
CANDIDATES = 3
MIN_TOP_UP_GWEI = 1_000_000_000


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def _select_candidates(raw, keys: list[dict], gateway, block_number: int) -> list[TopUpCandidate]:
    by_pubkey = {bytes.fromhex(k['key'][2:]): k for k in keys}
    data = extract_state_data(raw, set(by_pubkey))
    target_gwei = gateway.functions.getTargetBalanceGwei().call(block_identifier=block_number)
    epoch = raw.slot // SLOTS_PER_EPOCH

    selected = []
    for pubkey, index in sorted(data.pubkey_to_index.items(), key=lambda item: item[1]):
        fields = data.validators_fields[index]
        pending = data.pending_deposits.get(pubkey, 0)
        if fields.slashed or fields.activation_epoch > epoch or fields.exit_epoch != FAR_FUTURE_EPOCH:
            continue
        if index in data.consolidation_targets or int(raw.raw_state.balances[index]) + pending > target_gwei - MIN_TOP_UP_GWEI:
            continue
        key = by_pubkey[pubkey]
        selected.append(TopUpCandidate(index, key['index'], key['operatorIndex'], pubkey, pending))
        if len(selected) == CANDIDATES:
            break
    return selected


def main() -> None:
    w3 = Web3(HTTPProvider(os.environ['CAPTURE_EL'], request_kwargs={'timeout': 120}))
    cl_url = os.environ['CAPTURE_CL']
    cl = ConsensusClient(hosts=[cl_url], request_timeout=300, retry_total=3, retry_backoff_factor=2)
    kapi = os.environ['CAPTURE_KAPI']
    module_id = int(os.environ.get('CAPTURE_MODULE_ID', '4'))

    locator = w3.eth.contract(address=Web3.to_checksum_address(os.environ['CAPTURE_LOCATOR']), ContractFactoryClass=LidoLocatorContract)
    gateway = w3.eth.contract(address=locator.top_up_gateway(), ContractFactoryClass=TopUpGatewayContract)
    role_holder = gateway.functions.getRoleMembers(gateway.functions.TOP_UP_ROLE().call()).call()[0]

    fork_spec = _get_json(f'{cl_url}/eth/v1/config/spec')['data']
    gloas_pivot_slot = int(fork_spec['GLOAS_FORK_EPOCH']) * SLOTS_PER_EPOCH
    if gloas_pivot_slot != GLOAS_PIVOT_SLOT:
        sys.exit(f'run with GLOAS_PIVOT_SLOT={gloas_pivot_slot} (GLOAS_FORK_EPOCH from the CL spec)')
    raw = load_raw_beacon_state(w3, cl)
    if get_spec(raw.slot).__name__ != 'eth_consensus_specs.gloas.mainnet':
        sys.exit(f'state at slot {raw.slot} is not Gloas')

    anchor = w3.eth.get_block('latest')
    while anchor['timestamp'] > raw.timestamp:
        anchor = w3.eth.get_block(anchor['number'] - 1)
    if anchor['timestamp'] != raw.timestamp:
        sys.exit('anchor EL block not found')

    keys = _get_json(f'{kapi}/v1/modules/{module_id}/keys?used=true')['data']['keys']
    candidates = _select_candidates(raw, keys, gateway, anchor['number'])
    if not candidates:
        sys.exit('no eligible candidates')
    proof_data = build_topup_proofs(extract_state_data(raw, {c.pubkey for c in candidates}), candidates)

    tx = gateway.top_up(module_id, proof_data).build_transaction(
        {'from': role_holder, 'gas': 10_000_000, 'maxFeePerGas': 0, 'maxPriorityFeePerGas': 0, 'nonce': 0, 'chainId': w3.eth.chain_id}
    )
    call = {'from': role_holder, 'to': gateway.address, 'data': tx['data'], 'gas': hex(10_000_000)}
    w3.eth.call(call, block_identifier=anchor['number'])  # raises if the contract rejects the proofs
    prestate = w3.provider.make_request('debug_traceCall', [call, hex(anchor['number']), {'tracer': 'prestateTracer'}])['result']

    ssz_bytes = cl.get_beacon_state_ssz(raw.slot)
    (OUT_DIR / 'beacon_state.ssz').write_bytes(ssz_bytes)
    slot, proposer_index, parent_root, state_root, body_root = raw.header
    _write(
        'beacon_block_header.json',
        {
            'slot': slot,
            'proposer_index': proposer_index,
            'parent_root': '0x' + parent_root.hex(),
            'state_root': '0x' + state_root.hex(),
            'body_root': '0x' + body_root.hex(),
        },
    )
    _write(
        'execution_block.json',
        {
            'number': anchor['number'],
            'timestamp': anchor['timestamp'],
            'parentBeaconBlockRoot': '0x' + bytes(anchor['parentBeaconBlockRoot']).hex(),
        },
    )
    _write(
        'topup.json',
        {
            'module_id': module_id,
            'gateway': gateway.address,
            'role_holder': role_holder,
            'candidates': [
                {
                    'validator_index': c.validator_index,
                    'key_index': c.key_index,
                    'operator_id': c.operator_id,
                    'pubkey': '0x' + c.pubkey.hex(),
                    'pending_balance': c.pending_balance,
                }
                for c in candidates
            ],
            'proofs': [['0x' + node.hex() for node in w.proofs] for w in proof_data.witnesses],
        },
    )
    _write('prestate.json', prestate)
    _write(
        'meta.json',
        {
            'captured_at': datetime.now(UTC).isoformat(timespec='seconds'),
            'chain_id': w3.eth.chain_id,
            'el_client': w3.client_version,
            'gloas_fork_epoch': int(fork_spec['GLOAS_FORK_EPOCH']),
            'gloas_pivot_slot': gloas_pivot_slot,
            'locator': locator.address,
        },
    )
    print(f'captured slot={raw.slot} block={anchor["number"]} candidates={len(candidates)} prestate_accounts={len(prestate)}')


def _write(name: str, payload: dict) -> None:
    (OUT_DIR / name).write_text(json.dumps(payload, indent=2) + '\n')


if __name__ == '__main__':
    main()
