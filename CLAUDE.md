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

# Run integration tests (requires Holesky RPC in TESTNET_WEB3_RPC_ENDPOINTS and anvil installed)
poetry run pytest tests -m integration

# Lint and format
poetry run ruff check --fix
poetry run ruff format

# Type check
poetry run pyright src/

# Run a bot locally (dry mode, no transactions sent unless CREATE_TRANSACTIONS=true)
poetry run python src/main.py depositor
poetry run python src/main.py pauser
poetry run python src/main.py unvetter
```

## Git workflow

PRs target `develop` (the integration branch), not `main`. `main` is reserved for releases and occasional hotfixes. Always use `develop` as the base when diffing, reviewing, or creating PRs.

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
- **Onchain DataBus** (`src/transport/msg_providers/onchain_transport.py`) — Gnosis chain contract events parsed by `EventParser` subclasses (`DepositParser`, `PingParser`, etc.)

`MessageStorage` (`src/transport/msg_storage.py`) aggregates messages from all active transports, applies static filters (signature validity, checksum address normalization), and on each cycle calls `get_messages_and_actualize()` with a dynamic filter that discards messages older than 200 blocks or with a stale deposit root.

Quorum is formed by grouping valid messages by `blockHash`, then checking if any group has `>= guardian_quorum` unique guardian addresses.

### Deposit strategy and module ordering

`DepositorBot._get_preferred_to_deposit_modules()` sorts whitelisted staking modules by active validator count (fewest first) and iterates until it reaches the first "healthy" module — where healthy means: `can_deposit AND recent_quorum AND depositable_keys >= 1`. This ensures underfunded modules get deposits before overfunded ones.

Module 3 (Community Staking Module / CSM) uses `CSMDepositStrategy` instead of `DefaultDepositStrategy`. The key difference: CSM bypasses the gas-based deposit recommendation check — it always deposits if gas is below `MAX_GAS_FEE`.

The general strategy uses a cubic formula to compute a recommended gas ceiling: `(deposits_amount³ + 100) * 10⁸ wei`. More buffered keys → higher gas tolerance.

### Transaction sending

`TransactionUtils.send()` (`src/blockchain/web3_extentions/transaction.py`) builds an EIP-1559 transaction with dynamic gas estimation. If `RELAY_RPC` and `AUCTION_BUNDLER_PRIVATE_KEY` are configured, it attempts Flashbots relay first, falling back to classic broadcast on `PrivateRelayException`. When `CREATE_TRANSACTIONS=false` (default), the method logs and returns `True` without broadcasting — safe for dry runs.

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

## Testing

Unit tests (`-m unit`) are fully offline and run on every commit via pre-commit hook. Integration tests (`-m integration`) fork Holesky via anvil and require `TESTNET_WEB3_RPC_ENDPOINTS`.

`tests/conftest.py` provides shared fixtures including a mock `BlockData`, test council addresses, and a DSM owner account. Tests for each bot are in `tests/bots/`. Transport message schema tests are in `tests/transport/`.

`MessageStorage.messages` is a class-level list shared across instances — tests that don't call `storage.clear()` will leak messages into subsequent tests.

Pre-commit runs the full unit test suite on every commit (`poetry run pytest -m unit`). Never use `--no-verify` to skip it.

## Code style

- Line length: 140 characters
- Quotes: single quotes
- Ruff rules in effect: E, F, UP, B, SIM, I (B019 ignored)
- Pyright type checking covers `src/` only
