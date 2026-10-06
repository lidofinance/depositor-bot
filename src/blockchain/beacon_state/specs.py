"""Fork selection for beacon-state types (eth-consensus-specs: Fulu and Gloas)."""

from eth_consensus_specs.fulu import mainnet as fulu
from eth_consensus_specs.gloas import mainnet as gloas

from blockchain.beacon_state.constants import GLOAS_PIVOT_SLOT


def get_spec(slot: int):
    """Return the fork spec for a slot: Fulu before GLOAS_PIVOT_SLOT, Gloas from it (inclusive).

    The slot is known before the state is loaded (it comes in the header from the consensus
    client), so the type used to decode and to build proofs is chosen from it.
    """
    return gloas if slot >= GLOAS_PIVOT_SLOT else fulu
