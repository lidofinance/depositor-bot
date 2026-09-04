# Provenance: generated consensus-specs pyspec types

The `eth_consensus_specs/` directory next to this file contains **generated** Ethereum
consensus-specs Python containers (SSZ types) for the forks `phase0 … fulu, gloas`. It holds
types only — no service logic. Do not hand-edit; regenerate from the pinned commit below.
(This PROVENANCE.md lives one level up, outside `eth_consensus_specs/`, so `make regen-specs`
— which wipes and rewrites that directory — never touches it.)

## How to regenerate

Do this when you need a newer spec (e.g. the real Gloas fork rules land). From the repo root:

1. **Pick the new commit.** Open the consensus-specs repo, copy the full commit hash you want.

2. **Regenerate** (one command — needs `uv`, https://github.com/astral-sh/uv):

   ```bash
   make regen-specs CSPECS_COMMIT=<the-new-commit-hash>
   ```

   Without the Makefile, the same thing by hand:

   ```bash
   git clone https://github.com/ethereum/consensus-specs.git /tmp/cspecs
   cd /tmp/cspecs && git checkout <the-new-commit-hash>
   uv run --python 3.14 python -m pysetup.generate_specs --all-forks   # --all-forks is required
   ```

   then copy `tests/core/pyspec/eth_consensus_specs/` into `consensus-spec/eth_consensus_specs/`,
   keeping only what "What was copied" below lists.

3. **Update this file:** set the new commit hash and date under "Source", and the
   `CSPECS_COMMIT` default in the repo-root `Makefile`.

4. **Bump the deps if they changed.** Check `pyproject.toml` of the new consensus-specs commit
   and align the pins in our `pyproject.toml` (see "Runtime dependencies"), then `poetry lock`.

5. **Verify:** `poetry run pytest -m unit`. `test_validators_generalized_indices` pins the
   generalized indices (`validators` == 75 on Fulu, == 358 on Gloas); if a future spec changes the
   layout on purpose, update that test to the new expected values.

## Source

- Repository: https://github.com/ethereum/consensus-specs
- Commit: `09c77a4a74c2a21bea143486f06163581b4f5563`
- Generated: 2026-09-04
- Generator: `python -m pysetup.generate_specs --all-forks` (run via `uv`, CPython 3.14)
- consensus-specs package version at that commit: `eth-consensus-specs 1.7.0-beta.0`

`--all-forks` is required: `gloas` imports the phase0 → … → fulu chain.

## What was copied (from `tests/core/pyspec/eth_consensus_specs/`)

- `__init__.py`, `py.typed`
- per-fork `mainnet.py` + `__init__.py` for: phase0, altair, bellatrix, capella, deneb, electra, fulu, gloas
- `utils/` (excluding the two `test_*.py` files, which import `pytest` and are not used at runtime)
- `test/helpers/merkle.py` and the empty `test/__init__.py`, `test/helpers/__init__.py`
  (the generated `mainnet.py` imports `build_proof`/`get_generalized_index` from here)

Not copied: `minimal.py`, the rest of `test/`, `__pycache__`, other forks/EIP variants.

## Runtime dependencies (of the generated types, at import time)

`eth-ssz-specs`, `ckzg`, `py_arkworks_bls12381`, `blake3`, `frozendict`, `lru-dict`
— pinned in the repo `pyproject.toml`. The SSZ backend is `eth-ssz-specs` (import name `ssz`),
which supplies merkleization, generalized indices and proofs (ProgressiveContainer /
ProgressiveList for Gloas).

## How it's used

`src/blockchain/beacon_state/` puts `consensus-spec/` on `sys.path` and imports
`eth_consensus_specs.fulu.mainnet` / `eth_consensus_specs.gloas.mainnet`, selecting one by slot
(`get_spec`). Generalized indices pinned by tests: `validators` gindex == 75 (Fulu),
== 358 (Gloas).
