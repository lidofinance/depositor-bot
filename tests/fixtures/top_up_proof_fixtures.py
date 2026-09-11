import json
from pathlib import Path

import pytest

from blockchain.beacon_state.specs import get_spec

_FIXTURE_DIR = Path(__file__).resolve().parent / 'data' / 'top_up_proof'

# Decode the ~4 MB fixture state once per session (eth-ssz-specs values are immutable, so sharing
# the decoded state across tests is safe). Cached at module level rather than via a helper fixture,
# because only the names re-exported from tests/fixtures/__init__.py are registered as fixtures.
_DECODED_CACHE: tuple | None = None


def _decoded_top_up_state():
    global _DECODED_CACHE
    if _DECODED_CACHE is None:
        beacon_state_ssz = (_FIXTURE_DIR / 'beacon_state.ssz').read_bytes()
        beacon_block_header_json = json.loads((_FIXTURE_DIR / 'beacon_block_header.json').read_text())
        slot = int(beacon_block_header_json['slot'])
        spec = get_spec(slot)
        state = spec.BeaconState.decode_bytes(beacon_state_ssz)
        _DECODED_CACHE = (spec, state, beacon_state_ssz)
    return _DECODED_CACHE


@pytest.fixture
def top_up_proof_fixtures():
    """Offline fixture captured by top-up.py from srv3 CMv2 devnet (a Fulu state)."""
    spec, decoded_beacon_state, beacon_state_ssz = _decoded_top_up_state()

    execution_block = json.loads((_FIXTURE_DIR / 'execution_block.json').read_text())
    beacon_block_header_json = json.loads((_FIXTURE_DIR / 'beacon_block_header.json').read_text())
    proof_data = json.loads((_FIXTURE_DIR / 'proofs.json').read_text())

    beacon_block_header = (
        int(beacon_block_header_json['slot']),
        int(beacon_block_header_json['proposer_index']),
        bytes.fromhex(beacon_block_header_json['parent_root'][2:]),
        bytes.fromhex(beacon_block_header_json['state_root'][2:]),
        bytes.fromhex(beacon_block_header_json['body_root'][2:]),
    )

    return {
        'execution_block': execution_block,
        'beacon_block_header': beacon_block_header,
        'beacon_state_ssz': beacon_state_ssz,
        'spec': spec,
        'decoded_beacon_state': decoded_beacon_state,
        'validator_witnesses': proof_data['validatorWitnesses'],
        'proof_data': proof_data,
        'beacon_root_data': {
            'childBlockTimestamp': int(execution_block['timestamp']),
            'slot': beacon_block_header[0],
            'proposerIndex': beacon_block_header[1],
        },
    }
