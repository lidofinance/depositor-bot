# EDF guardian delegation (LIP-37 / DSM v5)

This document describes how the bot behaves when guardians are **delegation
contracts** instead of EOAs. Relevant from DSM `version() == 5` onward.

## The model

Before v5 a guardian is a plain EOA: it signs council messages with its own key
and is recovered on-chain with `ecrecover`.

From v5 a guardian is an ERC-1271 **contract**. The key that actually signs
messages and posts them to the Data Bus is the guardian's **delegate EOA**, which
the guardian owner can rotate, revoke, or terminate. `getDelegate()` returns the
*currently effective* delegate (zero address if none).

Two distinct identities result, and both matter:

- **guardian (contract)** — the stable identity used for quorum and dedup.
- **delegate (EOA)** — the ephemeral signer, carried on each message as
  `guardianDelegate` so freshness can be re-checked downstream.

The bot never holds any of these keys. It only receives already-signed messages,
verifies them, reshapes the signatures, and submits them (paying gas with its own
tx key).

## The version switch

Everything is driven by the on-chain DSM version, never by a config flag — so it
cannot desync from chain state.

- `GUARDIAN_DELEGATION_DSM_VERSION = 5` (`lido_contracts.py`).
- `LidoContracts.guardian_delegation_active()` → `dsm_version >= 5`. This single
  boolean (`delegated`) gates all three touchpoints below.
- `DSM_CONTRACT_BY_VERSION` maps `4 → DepositSecurityModuleContract`,
  `5 → DepositSecurityModuleContractV5`. Adding a key here is what "supports" a
  version; an unmapped version fails to boot.

Below v5 the delegation code paths degrade to exact legacy behavior (see each
section) — `getDelegate()` is never called (it would revert on an EOA).

## The three touchpoints

### 1. Transport — Data Bus reception (`onchain_transport.py`)

The Data Bus event `sender` is the delegate EOA. The provider:

- Builds `{delegate_EOA: guardian_contract}` via
  `LidoContracts.get_guardian_delegates()` and filters Data Bus logs by the
  **delegate** addresses (indexed topic).
- On receipt, reverse-maps `sender → guardian` and stores both:
  `guardianAddress = guardian`, `guardianDelegate = delegate`.
- The map is snapshotted once per fetch and reused for the reverse map, so the
  topic filter and the lookup always agree. A `sender` with no mapping is dropped
  (fail closed) — only reachable if a delegate rotates out mid-fetch.

**Below v5** `get_guardian_delegates()` returns the identity map
`{guardian: guardian}`, so the filter targets guardians and the reverse map is a
no-op — byte-for-byte the pre-EDF path.

### 2. Verification — off-chain sign filter (`msg_types/common.py`)

`get_messages_sign_filter(prefix, delegated=...)` mirrors the on-chain check:

- **delegated**: the signed digest folds in the guardian contract address —
  `keccak(prefix, guardian, ...fields)` — and the recovered signer must equal
  `guardianDelegate`. This is the off-chain twin of the on-chain ERC-1271 →
  `getDelegate()` check.
- **below v5**: legacy digest `keccak(prefix, ...fields)`, signer must equal
  `guardianAddress`.

Because `getDelegate()` is read fresh (subject to the TTL cache below), a message
from a rotated/revoked delegate stops verifying — the fail-closed backstop.

### 3. Submission — signature reshaping (`cryptography/verify_signature.py`)

Council messages always carry the compact `(r, _vs)` pair.
`to_guardian_signature(guardian, r, vs, delegated)` reshapes it for the DSM call
— it does **not** sign anything:

- **delegated**: `(guardian_contract, 65-byte r‖s‖v blob)` — the `GuardianSignature`
  struct. The 65-byte layout is what ERC-1271 / OpenZeppelin `ECDSA.recover`
  expects; the guardian address is explicit because recovery yields the delegate,
  not the guardian.
- **below v5**: the compact `(r, _vs)` pair, recovered on-chain to the guardian
  EOA.

Signatures are still sorted ascending by guardian address before submission.
`deposit_transaction_sender.py` (deposit), `pauser.py`, and `unvetter.py` all pass
`guardian_delegation_active()` as `delegated`.

## Freshness and caching

`getDelegate()` is called per guardian; the resolved delegate map is memoized for
`GUARDIAN_DELEGATES_CACHE_TTL` seconds (default `60`) to bound EL-provider load —
the map is otherwise rebuilt on every module/quorum pass. The cache is a
throughput optimization, not the correctness boundary: a stale delegate only
widens the window in which a rotated-out delegate's message could pass the
off-chain filter, and the DSM still verifies the delegate on-chain at submission
time.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GUARDIAN_DELEGATES_CACHE_TTL` | `60` | Seconds to memoize the `{delegate: guardian}` map. |

No flag enables the feature — it activates automatically at DSM `version() == 5`.

## Interfaces

- `interfaces/Guardian.json` — minimal ABI, only `getDelegate()`.
- `interfaces/DepositSecurityModuleV5.json` — v5 DSM ABI (compiled from
  `lidofinance/core@feat/edf`), used when `version() == 5`.
