import json
from pathlib import Path

import pytest
from blockchain.beacon_state.ssz_types import BeaconState
from blockchain.beacon_state.state import compute_state_field_roots
from ssz import decode  # type: ignore[attr-defined]


@pytest.fixture
def top_up_proof_fixtures():
    """Offline fixture captured by top-up.py from srv3 CMv2 devnet."""
    fixture_dir = Path(__file__).resolve().parent / 'data' / 'top_up_proof'

    beacon_state_ssz = (fixture_dir / 'beacon_state.ssz').read_bytes()
    execution_block = json.loads((fixture_dir / 'execution_block.json').read_text())
    beacon_block_header_json = json.loads((fixture_dir / 'beacon_block_header.json').read_text())
    proof_data = json.loads((fixture_dir / 'proofs.json').read_text())
    decoded_beacon_state = decode(beacon_state_ssz, BeaconState)

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
        'decoded_beacon_state': decoded_beacon_state,
        'beacon_state_field_roots': compute_state_field_roots(decoded_beacon_state),
        'validator_witnesses': proof_data['validatorWitnesses'],
        'proof_data': proof_data,
        'beacon_root_data': {
            'childBlockTimestamp': int(execution_block['timestamp']),
            'slot': beacon_block_header[0],
            'proposerIndex': beacon_block_header[1],
        },
    }
