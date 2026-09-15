"""Service-level constants for beacon-state handling.

Consensus constants that the service logic needs directly (epoch math, sentinels)
live here so strategies don't have to hold a fork `spec` object just to read a number.
They are invariant across the forks we support (Fulu, Gloas).
"""

import os

SLOTS_PER_EPOCH = 32
FAR_FUTURE_EPOCH = 2**64 - 1

# Sentinel slot meaning "never" (max uint64).
FAR_FUTURE_SLOT = 2**64 - 1

# First slot of the Gloas activation epoch: GLOAS_FORK_EPOCH * SLOTS_PER_EPOCH.
# At/after this slot the state is decoded and proven as Gloas (ProgressiveContainer /
# ProgressiveList); before it, as Fulu.
#
# Set per network via the GLOAS_PIVOT_SLOT env var (e.g. a Gloas devnet with GLOAS_FORK_EPOCH=1536
# -> GLOAS_PIVOT_SLOT=49152). Unset defaults to "never", so the service stays on Fulu until the
# mainnet fork epoch is known.
GLOAS_PIVOT_SLOT = int(os.getenv('GLOAS_PIVOT_SLOT', str(FAR_FUTURE_SLOT)))
