"""Fork selection for beacon-state types.

The generated consensus-specs containers (Fulu, Gloas, and the phase0..fulu chain they import)
live under ``consensus-spec/eth_consensus_specs`` and are put on sys.path by this package's
__init__. They are generated from the official spec — never hand-edited (see PROVENANCE.md there).
"""

from eth_consensus_specs.fulu import mainnet as fulu
from eth_consensus_specs.gloas import mainnet as gloas

from blockchain.beacon_state.constants import GLOAS_PIVOT_SLOT


def get_spec(slot: int):
    """Return the fork spec for a slot: Fulu before GLOAS_PIVOT_SLOT, Gloas from it (inclusive).

    The slot is known before the state is loaded (it comes in the header from the consensus
    client), so the type used to decode and to build proofs is chosen from it.
    """
    return gloas if slot >= GLOAS_PIVOT_SLOT else fulu
