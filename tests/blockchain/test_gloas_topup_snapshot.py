"""Gloas top-up proofs against what the deployed TopUpGateway accepts.

The snapshot in fixtures/data/top_up_proof_gloas was captured from a Gloas devnet by capture.py there:
the beacon state, the anchor header/EL block, the candidates, the proofs, and the prestate of every
account TopUpGateway.topUp touches. topUp was simulated on the devnet before anything was written,
so the stored proofs are ones the contract accepted.

- the unit test pins the bot's proofs to those bytes (offline, every commit);
- the integration test replays topUp against the real contract bytecode on a local anvil loaded with
  the prestate, so the contract itself verifies the proofs without the devnet.
"""

import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fork import anvil_fork
from web3 import HTTPProvider, Web3

from blockchain.beacon_state.state import BeaconStateData, extract_state_data, load_raw_beacon_state
from blockchain.contracts.topup_gateway import TopUpGatewayContract
from blockchain.topup.proofs import build_topup_proofs
from blockchain.topup.types import TopUpCandidate, TopUpProofData

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / 'fixtures' / 'data' / 'top_up_proof_gloas'
INVALID_PROOF_SELECTOR = '0x09bde339'  # InvalidProof()
ANVIL_PORT = '8546'


def _read(name: str) -> dict:
    return json.loads((SNAPSHOT_DIR / name).read_text())


@pytest.fixture(scope='module')
def snapshot() -> dict:
    return {
        'header': _read('beacon_block_header.json'),
        'block': _read('execution_block.json'),
        'topup': _read('topup.json'),
        'prestate': _read('prestate.json'),
        'meta': _read('meta.json'),
    }


@pytest.fixture(scope='module')
def beacon_data(snapshot) -> BeaconStateData:
    """The snapshot state run through the production loader, as the bot would at the anchor block."""
    header, block = snapshot['header'], snapshot['block']
    w3 = MagicMock()
    w3.eth.get_block.return_value = {
        'parentBeaconBlockRoot': bytes.fromhex(block['parentBeaconBlockRoot'][2:]),
        'timestamp': block['timestamp'],
    }
    cl = MagicMock()
    cl.get_block_header.return_value = {key: str(value) for key, value in header.items()}
    cl.get_beacon_state_ssz.return_value = (SNAPSHOT_DIR / 'beacon_state.ssz').read_bytes()

    with patch('blockchain.beacon_state.specs.GLOAS_PIVOT_SLOT', snapshot['meta']['gloas_pivot_slot']):
        raw = load_raw_beacon_state(w3, cl)
        pubkeys = {bytes.fromhex(c['pubkey'][2:]) for c in snapshot['topup']['candidates']}
        yield extract_state_data(raw, pubkeys)


@pytest.fixture(scope='module')
def proof_data(snapshot, beacon_data) -> TopUpProofData:
    candidates = [
        TopUpCandidate(
            validator_index=c['validator_index'],
            key_index=c['key_index'],
            operator_id=c['operator_id'],
            pubkey=bytes.fromhex(c['pubkey'][2:]),
            pending_balance=c['pending_balance'],
        )
        for c in snapshot['topup']['candidates']
    ]
    with patch('blockchain.beacon_state.specs.GLOAS_PIVOT_SLOT', snapshot['meta']['gloas_pivot_slot']):
        return build_topup_proofs(beacon_data, candidates)


@pytest.mark.unit
def test_gloas_state_loads_through_production_path(snapshot, beacon_data):
    assert type(beacon_data.raw_state).__module__ == 'eth_consensus_specs.gloas.mainnet'
    assert beacon_data.slot == snapshot['header']['slot']
    assert set(beacon_data.pubkey_to_index.values()) == {c['validator_index'] for c in snapshot['topup']['candidates']}


@pytest.mark.unit
def test_gloas_proofs_match_contract_accepted_snapshot(snapshot, proof_data):
    built = [['0x' + node.hex() for node in w.proofs] for w in proof_data.witnesses]
    assert built == snapshot['topup']['proofs']


def _state_override(prestate: dict) -> dict:
    return {
        address: {
            'balance': account.get('balance', '0x0'),
            'nonce': hex(account.get('nonce', 0)),
            'code': account.get('code', '0x'),
            'state': account.get('storage', {}),
        }
        for address, account in prestate.items()
    }


@pytest.fixture(scope='module')
def snapshot_chain(snapshot):
    """A fresh local anvil; the snapshot prestate and the anchor block's number/time are applied per call."""
    # --silent: anvil_fork pipes stdout without draining it; anvil's per-revert request dumps would fill the pipe and stall it.
    local_args = ('--silent', '--no-mining', '--chain-id', str(snapshot['meta']['chain_id']))
    with anvil_fork(os.getenv('ANVIL_PATH', ''), None, port=ANVIL_PORT, local_args=local_args):
        yield Web3(HTTPProvider(f'http://127.0.0.1:{ANVIL_PORT}', request_kwargs={'timeout': 120}))


def _simulate_top_up(w3: Web3, snapshot: dict, proof_data: TopUpProofData) -> dict:
    """eth_call topUp as of the anchor block: its state (prestate override) and its number/timestamp (block override)."""
    topup, block = snapshot['topup'], snapshot['block']
    gateway = w3.eth.contract(address=Web3.to_checksum_address(topup['gateway']), ContractFactoryClass=TopUpGatewayContract)
    sender = Web3.to_checksum_address(topup['role_holder'])
    calldata = gateway.top_up(topup['module_id'], proof_data).build_transaction(
        {'from': sender, 'gas': 10_000_000, 'nonce': 0, 'maxFeePerGas': 0, 'maxPriorityFeePerGas': 0, 'chainId': w3.eth.chain_id}
    )['data']
    call = {'from': sender, 'to': gateway.address, 'data': calldata, 'gas': hex(10_000_000)}
    block_override = {'number': hex(block['number']), 'time': hex(block['timestamp'])}
    return w3.provider.make_request('eth_call', [call, 'latest', _state_override(snapshot['prestate']), block_override])


@pytest.mark.integration
def test_gloas_topup_accepted_by_contract(snapshot_chain, snapshot, proof_data):
    response = _simulate_top_up(snapshot_chain, snapshot, proof_data)
    assert 'error' not in response, response['error']


@pytest.mark.integration
def test_gloas_topup_tampered_proof_rejected_by_contract(snapshot_chain, snapshot, proof_data):
    # Guards the test above against passing vacuously: the replayed contract must actually verify proofs.
    first, *rest = proof_data.witnesses
    proofs = list(first.proofs)
    proofs[3] = bytes([proofs[3][0] ^ 1]) + proofs[3][1:]
    tampered = replace(proof_data, witnesses=[replace(first, proofs=proofs), *rest])

    response = _simulate_top_up(snapshot_chain, snapshot, tampered)
    assert response.get('error', {}).get('data') == INVALID_PROOF_SELECTOR
