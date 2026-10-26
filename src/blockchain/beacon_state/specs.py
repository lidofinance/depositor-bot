"""Fork selection for beacon-state types (eth-consensus-specs: Fulu and Gloas)."""

from eth_consensus_specs.fulu import mainnet as fulu
from eth_consensus_specs.gloas import mainnet as gloas

from blockchain.beacon_state.constants import SLOTS_PER_EPOCH


def get_spec(slot: int, gloas_fork_epoch: int):
    """Return the fork spec for a slot: Fulu before the Gloas fork epoch, Gloas from it (inclusive).

    The slot is known before the state is loaded (it comes in the header from the consensus
    client), so the type used to decode and to build proofs is chosen from it. gloas_fork_epoch
    is GLOAS_FORK_EPOCH from the CL /eth/v1/config/spec (FAR_FUTURE_EPOCH while not scheduled).
    """
    return gloas if slot // SLOTS_PER_EPOCH >= gloas_fork_epoch else fulu
