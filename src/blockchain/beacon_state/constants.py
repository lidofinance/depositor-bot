"""Service-level constants for beacon-state handling.

Consensus constants that the service logic needs directly (epoch math, sentinels)
live here so strategies don't have to hold a fork `spec` object just to read a number.
They are invariant across the forks we support (Fulu, Gloas).
"""

SLOTS_PER_EPOCH = 32
FAR_FUTURE_EPOCH = 2**64 - 1

# Sentinel slot meaning "never" (max uint64).
FAR_FUTURE_SLOT = 2**64 - 1
