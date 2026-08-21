# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
poetry install --with dev
poetry run pre-commit install

# Run all unit tests
poetry run pytest tests -m unit

# Run a single test file or test
poetry run pytest tests/bots/test_depositor.py -m unit
poetry run pytest tests/bots/test_depositor.py::TestDepositorBot::test_name -m unit

# Run integration tests (requires Hoodi RPC in TESTNET_WEB3_RPC_ENDPOINTS and anvil installed)
poetry run pytest tests -m integration

# Lint and format — use the pre-commit hooks, NOT `poetry run ruff`.
# The hooks pin ruff v0.15.9; the dev dependency resolves to 0.4.10, whose isort classifies
# `schema`/`web3` as first-party and rewrites the import block of nearly every file in the repo.
# Running `poetry run ruff check --fix` therefore produces a large unrelated diff that the pinned
# version then leaves untouched.
poetry run pre-commit run ruff --files <changed files>
poetry run pre-commit run ruff-format --files <changed files>
poetry run pre-commit run --all-files

# Type check (48 errors are pre-existing — compare against the base commit, don't chase the total)
poetry run pyright src/

# Run a bot locally (dry mode, no transactions sent unless CREATE_TRANSACTIONS=true)
poetry run python src/main.py depositor
poetry run python src/main.py pauser
poetry run python src/main.py unvetter
```

## Protocol concepts

Understanding these is essential before changing any bot logic.

### Why deposits exist and the front-running problem

When users stake ETH via Lido it accumulates in a buffer. To activate validators on the Beacon Chain, that ETH must be sent to Ethereum's deposit contract paired with a validator pubkey and withdrawal credentials. The attack Lido defends against: an attacker watching the mempool could see a pending Lido deposit for pubkey X, front-run it with their own deposit for pubkey X but with *their* withdrawal credentials, and then Lido's tx goes through activating a validator whose rewards go to the attacker.

The DSM prevents this by requiring a quorum of Council Daemon guardians to sign over `(depositRoot, blockHash, nonce)` at a specific block. If anyone else has deposited since that block (changing `depositRoot`), the DSM contract reverts. The depositor bot's job is to collect enough of those signatures, verify they still match the current chain state, and submit the deposit tx.

One detail: guardian signatures are **sorted by address (ascending)** before submission — `Sender._prepare_signs_for_deposit()` does this. The DSM contract requires it for efficient duplicate checking.

### Pausing

Council Daemons monitor for validator key theft. When they detect it, they broadcast signed pause messages. The PauserBot receives any single valid guardian pause message and immediately calls `pauseDeposits()` on the DSM — only **one** signature is needed, not a quorum, because stopping quickly is more important than consensus.

- PauserBot runs every block (`blocks_between_execution = 1`), unlike the depositor which can wait.
- Pause messages expire after `getPauseIntentValidityPeriodBlocks()` blocks — stale ones are discarded.
- **DSMv1**: pause is per-module — `pauseDeposits(blockNumber, moduleId, signature)`. Message must contain `stakingModuleId`.
- **DSMv2**: pause is global — `pauseDepositsV2(blockNumber, signature)`. Message must *not* contain `stakingModuleId`.
- The version-routing logic is in `PauserBot._send_pause_message()`.

### Unvetting

Node operators pre-submit validator signing keys to StakingRouter to get them approved ("vetted") for future deposits. If a key is later found to be invalid or compromised, Council Daemons broadcast an unvet message. The UnvetterBot calls `unvetSigningKeys()` on DSM to reduce the approved key count for specified operators.

- Only supported on DSMv2 — UnvetterBot skips silently on v1.
- `operatorIds` is ABI-packed as `uint64[]` — each operator ID occupies 8 bytes, which is why the count check is `len(operator_ids) / 8`.
- `vettedKeysByOperator` is similarly packed — the new (lower) approved count per operator.
- A single tx is capped at `getMaxOperatorsPerUnvetting()` operators.
- Nonce filter: messages with `nonce < current_module_nonce` are discarded (the state has already advanced past them).

### Guardian delegation (EDF / LIP-37, DSM v5)

From DSM `version() == 5` a guardian is no longer an EOA but an ERC-1271 **delegation contract**. A rotatable **delegate EOA** (`getDelegate()`) is what signs council messages and posts to the Data Bus. The guardian contract stays the identity used for quorum/dedup; the delegate is the signer. The bot holds none of these keys — it receives, verifies, reshapes, and submits already-signed messages.

- The switch is driven entirely by the on-chain version, never a flag: `LidoContracts.guardian_delegation_active()` (`dsm_version >= GUARDIAN_DELEGATION_DSM_VERSION`, `=5`). This one boolean (`delegated`) gates all delegation behavior. `DSM_CONTRACT_BY_VERSION` in `lido_contracts.py` is what "supports" a version — the bot now boots on both v4 and v5.
- **Below v5 the delegation paths are exact no-ops**: the delegate map resolves to `{guardian: guardian}`, the digest/verification stay legacy, `getDelegate()` is never called (it would revert on an EOA). Don't add v5 special-casing without preserving this.
- Three touchpoints, all gated by `delegated`: (1) Data Bus reception reverse-maps `sender → guardian` (`onchain_transport.py`); (2) off-chain sign filter folds the guardian address into the digest and checks the signer against the delegate (`msg_types/common.py`); (3) `to_guardian_signature` reshapes the compact `(r,_vs)` into the v5 `GuardianSignature` `(guardian, r‖s‖v)` — it does **not** sign (`cryptography/verify_signature.py`).
- The `{delegate: guardian}` map is memoized for `GUARDIAN_DELEGATES_CACHE_TTL` seconds (default 60). Freshness backstop is the on-chain check at submission, not the cache.
- **Full details: `docs/edf-guardian-delegation.md`.** Read it before touching signature shaping, the sign filter, or Data Bus sender handling.

## Architecture

### Entry point and Web3 extension pattern

`src/main.py` accepts a single CLI argument (`depositor`, `pauser`, or `unvetter`) and wires up shared infrastructure before delegating to the appropriate `run_*` function in `src/bots/`.

The key architectural choice is that contracts and transaction utilities are attached as **Web3 modules**:

```python
w3.attach_modules({'lido': LidoContracts, 'transaction': TransactionUtils})
```

This means all contract access throughout the codebase goes through `w3.lido.<contract>.<method>()` and transaction sending through `w3.transaction.send(...)`. `LidoContracts` (`src/blockchain/web3_extentions/lido_contracts.py`) resolves all contract addresses at startup via `LidoLocator`, and handles V1/V2 version detection for `StakingRouter` and `DepositSecurityModule` by querying `get_contract_version()` / `version()` and instantiating the appropriate contract class.

### Execution loop

Each bot is driven by `Executor` (`src/blockchain/executor.py`), which polls for new blocks and calls `bot.execute(block)` on each cycle. The return value matters: `True` advances by `BLOCKS_BETWEEN_EXECUTION` blocks (normal operation), `False` retries on the very next block.

### Message transport and quorum logic (Depositor)

Council Daemon guardians broadcast signed messages over one or both transports:
- **RabbitMQ** (`src/transport/msg_providers/rabbit.py`) — STOMP protocol
- **Onchain DataBus** (`src/transport/msg_providers/onchain_transport.py`) — Gnosis chain contract events parsed by `EventParser` subclasses (`DepositV1Parser`, `PingParser`, etc.)

#### DataBus message generations (council v4 / v5)

Two generations of DataBus events are live at once, because the change is rolled out council by council:

| | council v4 | council v5 |
|---|---|---|
| deposit | `MessageDepositV1` | `MessageDepositV2` |
| pause | `MessagePauseV3` | `MessagePauseV4` |
| unvet | `MessageUnvetV1` | `MessageUnvetV2` |
| ping | `MessagePingV1` | `MessagePingV1` (unchanged, unsigned) |

The only difference is the guardian signature: v4 events carry the compact `(bytes32 r, bytes32 vs)` pair, v5 events carry a flat 65-byte `bytes` blob (`r ‖ s ‖ v`) — the shape DSMv5 verifies via ERC-1271. Parsers normalise the blob back into `(r, _vs)` (`compact_signature` in `src/cryptography/verify_signature.py`), so **nothing downstream is version-aware**: one internal signature representation serves RabbitMQ, the sign filter and both DSM versions.

Both parser sets are registered in each bot (`parsers_providers=[...]`). **Cleanup after the on-chain rollout completes: delete the V1/V3 parsers and their tests.**

Logs are dispatched to the parser that declared their event id (`topic0`), never by trying parsers until one does not raise — the V1 layout decodes a V2 payload *without* raising (the ABI offset word reads as `blockNumber`), so a fallback chain would silently turn every v5 message into garbage that only fails later, at signature verification.

`MessageStorage` (`src/transport/msg_storage.py`) aggregates messages from all active transports, applies static filters, and on each cycle calls `get_messages_and_actualize()` with a dynamic filter.

The split between the two filter lists is load-bearing, not cosmetic: **static filters run once per message, on arrival; the actualize filter re-runs over the entire retained list on every call** — and `_fetch_actual_messages()` is called once per whitelisted module per cycle (`_refresh_modules_state`), plus once more per deposit attempt. So anything whose answer cannot change belongs in the static list, or it gets paid for N times per cycle per retained message.

- **Static** (`DepositorBot.__init__`): metrics/type filter, checksum normalization, then **guardian signature verification** — a property of the message alone (the digest covers every signed field; the attest prefix and delegation mode are fixed for the process, both changing only on a DSM upgrade, which already requires a restart). Order matters: the sign filter must follow `to_check_sum_address`, since it compares against the recovered (checksummed) address.
- **Actualize** (`_get_message_actualize_filter`): only checks against mutable chain state — guardian/delegate still registered, deposit root still current, and `blockNumber` within `MESSAGE_BLOCK_WINDOW` (200) of the node's head **in either direction**. The upper bound matters: `blockNumber` is inside the signed digest, so without it a guardian could sign unlimited messages for blocks the chain will never reach, each retained forever under "cannot verify yet" — unbounded storage growth that eventually pushes a cycle past `MAX_CYCLE_LIFETIME_IN_SECONDS` and kills the daemon, taking down the quorum-free top-up path with it.

Quorum is formed by grouping valid messages by `blockHash`, then checking if any group has `>= guardian_quorum` unique guardian addresses.

### Deposit strategy and module ordering

`DepositorBot._get_preferred_to_deposit_modules()` sorts whitelisted staking modules by active validator count (fewest first) and iterates until it reaches the first "healthy" module — where healthy means: `can_deposit AND recent_quorum AND depositable_keys >= 1`. This ensures underfunded modules get deposits before overfunded ones.

Module 3 (Community Staking Module / CSM) uses `CSMDepositStrategy` instead of `DefaultDepositStrategy`. The key difference: CSM bypasses the gas-based deposit recommendation check — it always deposits if gas is below `MAX_GAS_FEE`.

The general strategy uses a cubic formula to compute a recommended gas ceiling: `(deposits_amount³ + 100) * 10⁸ wei`. More buffered keys → higher gas tolerance.

### Transaction sending

`TransactionUtils.send()` (`src/blockchain/web3_extentions/transaction.py`) builds an EIP-1559 transaction with dynamic gas estimation. If `RELAY_RPC` and `AUCTION_BUNDLER_PRIVATE_KEY` are configured, it attempts Flashbots relay first, falling back to classic broadcast on `PrivateRelayException`. When `CREATE_TRANSACTIONS=false` (default), the method logs and returns `True` without broadcasting — safe for dry runs.

#### Delegated execution (EDF, LIP-37)

`TopUpGateway.topUp` is the **only** permissioned call the bot makes (`TOP_UP_ROLE`, AccessControl). It can be sent by either identity, and **which one is used is resolved from chain state, not from configuration** — `DepositorBot._resolve_topup_path()`, once per iteration:

| resolved path | condition |
|---|---|
| `delegated` | `DELEGATION_CONTRACT_ADDRESS` holds `TOP_UP_ROLE`, is not terminated, and the bot's key is its active delegate → tx wrapped as `delegation.execute(topUpGateway, <topUp calldata>)` (`DelegationContract.wrap()`) |
| `direct` | otherwise, and the bot's own account holds the role → plain `topUp` call |
| `not_delegate` / `terminated` / `no_role` | nothing can execute; see the gate ladder below |

Delegation is preferred and the key is the fallback, so migrating the role in either direction needs no restart timed to the `grantRole`/`revokeRole` transactions — the bot follows the role on its next cycle. Same idea as `SignerModule.process_members` in lido-oracle, which resolves the active identity from the HashConsensus member list each cycle. With the role on the delegation contract, rotating the bot's key becomes a `nominateDelegate` by the contract's owner instead of an ACL change on TopUpGateway.

Startup refuses to boot only when a delegation contract *is* configured and no path can execute. `no_role` with no delegation configured is the pre-existing "role was never granted to the key" mistake — now visible on the metric, but kept a warning so upgrading a running deployment can't turn into a boot failure.

Wrapping happens **before** `transaction.check()`/gas estimation, so the dry-run simulates what actually gets mined; simulating the unwrapped call would revert with `AccessControlUnauthorizedAccount`.

Deposits, pause and unvet are deliberately **not** wrapped. DSM v5 authorises `depositBufferedEther` purely from the guardian signatures in calldata — it never reads `msg.sender` — so wrapping would only add gas and couple deposits to delegate state. `pauseDeposits`/`unvetSigningKeys` do have a `msg.sender`-is-guardian branch, but the bot always holds a signed council message, so the signature path is always open to it and making its hot key a guardian delegate would let that key pause deposits with no quorum.

### Logging convention

All log calls use structured dict format:
```python
logger.info({'msg': 'Human readable description.', 'value': some_value})
```
Never use f-strings directly in `logger.*` calls; always put the message in the `msg` key.

### Adding configuration variables

All environment variables are read in `src/variables.py`. When adding a new one:
1. Add it to `src/variables.py`
2. Add it to `README.md`'s variable table
3. Add it to `.env.example`
4. If non-sensitive, include it in the `PUBLIC_ENV_VARS` dict (logged at startup)

### Python import root

`pyproject.toml` sets `pythonpath = ["src", "tests"]`. All imports are relative to `src/` — use `from blockchain.contracts...`, not `from src.blockchain...`.

## Debugging: "why wasn't key X deposited / topped up?"

This question splits into two different investigations depending on what X is. Conflating them
wastes time — figure out which one applies before looking at anything.

### X is an already-active validator (top-up path)

CMv2 evaluates individual pubkeys for top-up, so there's always a definitive, instrumented answer.
Walk the gates in order; the first one that isn't "pass" is almost always the whole answer.

Module-level gates (Prometheus, defined in `src/metrics/metrics.py`, set in `src/bots/depositor.py`):

1. `topup_gateway_paused == 0` (and `variables.ENABLE_TOP_UP` is true — checked at startup, not a metric).
2. `topup_execution_path` is `direct` or `delegated` — both healthy, and which one is live tells you
   where `TOP_UP_ROLE` currently sits. `not_delegate` / `terminated` / `no_role` each make *every*
   top-up revert. Seeing one at runtime means the role assignment changed under a running bot
   (delegate rotated or revoked, contract terminated, role removed from both identities). Resolved
   before every early return in `_execute_actual()` (alongside `topup_gateway_paused`), so it stays
   trustworthy on idle iterations — an empty buffer would otherwise freeze it at its last value.
3. `module_allocation_wei{module_id, kind="topup"} > 0`. Zero here is the single most common reason
   nothing happens — the StakingRouter allocation algorithm didn't route ETH to this module at all
   this cycle.
4. `module_stake_wei{module_id, kind="topup"}` — lowest value across candidate modules goes first.
   Only **one** module is acted on per bot iteration (`_phase_full_and_topup` returns on the first
   non-`SKIPPED` outcome), so a module that lost the priority race this cycle never gets its
   `phase_outcome`/`quorum_state` touched — those stay at whatever they were last time this module
   *was* reached. Tell "evaluated and skipped" from "not reached this cycle" by comparing
   `phase_last_run_timestamp_seconds{phase="B", module_id}` against `module_allocation_wei`'s own
   freshness (both are set every cycle regardless of whether the module becomes a candidate).
5. `topup_gas_ok{module_id}` / `topup_gas_fee_wei{type}`.
6. `phase_outcome{phase="B", module_id} != wait_distance` (TopUpGateway block distance).

Key-level gates — module_id is now known, question narrows to pubkey X. Instrumented in
`CMv2TopUpStrategy` (`src/blockchain/topup/cmv2_strategy.py`), evaluated in this order:

- `not_in_beacon_state` / `not_active` / `slashed` / `exiting` / `beacon_consolidation_target` /
  `already_at_target_balance` — `_check_key_eligibility`.
- `pending_consolidation_bus` — excluded by a pending ConsolidationBus request.
- `operator_budget_exhausted` — eligible and funded in isolation, but the operator's allocation ran
  out before reaching X in validator-index order (`_take_up_to_allocation`). This is a queue-position
  problem, not an eligibility problem — X is a strong candidate for the next cycle.
- `truncated_by_max_validators` — eligible, funded, and within its operator's budget, but cut by the
  cross-operator `max_validators` cap on the final sorted list.

**`topup_key_excluded_total{module_id, reason}` (Counter) only tells you a reason is trending up —
it is deliberately not labeled by pubkey** (would explode cardinality across thousands of keys).
For "why was key X specifically excluded," grep logs for the structured line every excluded
candidate gets, once per cycle, from `_log_excluded_key`:

```
{"msg": "Top-up candidate excluded.", "module_id": ..., "operator_id": ..., "pubkey": "0x...", "reason": "..."}
```

### X has never been deposited (first-deposit / 0x01 path)

The bot does **not** pick a specific key here — it only decides how much ETH to route to X's
*module* via `depositBufferedEther`. Which key gets consumed next is decided on-chain by that
module's registry contract (NodeOperatorsRegistry / CSM), based on operator stake share and key
submission order. That logic lives outside this repo and this repo has no metric for it — don't go
looking for one.

Check, in order: `deposits_paused`, `depositable_ether`, `module_status{module_id}` +
`module_allocation_wei{module_id, kind="seed"}`, `quorum_state{module_id}` (deposits require a
signed guardian quorum; top-ups don't — this gate has no equivalent on the top-up path),
`phase_outcome{phase, module_id}`.

If all of those pass and a deposit was sent, the module is healthy and the bot did its job — whether
X specifically was the key consumed requires a separate lookup outside this bot: compare X's key
index for its operator (Keys API) against the operator's currently-used-key count and stake share
(StakingRouter). That's a one-off chain-state query, not something worth turning into a bot metric —
it doesn't change cycle to cycle the way allocation or gas does.

## Testing

Unit tests (`-m unit`) are fully offline and run on every commit via pre-commit hook. Integration tests (`-m integration`) fork Hoodi via anvil and require `TESTNET_WEB3_RPC_ENDPOINTS`.

`tests/conftest.py` provides shared fixtures including a mock `BlockData`, test council addresses, and a DSM owner account. Tests for each bot are in `tests/bots/`. Transport message schema tests are in `tests/transport/`.

`MessageStorage.messages` is a class-level list shared across instances — tests that don't call `storage.clear()` will leak messages into subsequent tests.

Pre-commit runs the full unit test suite on every commit (`poetry run pytest -m unit`). Never use `--no-verify` to skip it.

## Code style

- Line length: 140 characters
- Quotes: single quotes
- Ruff rules in effect: E, F, UP, B, SIM, I (B019 ignored)
- Pyright type checking covers `src/` only
