# EDF / DSM v5 test chain

`upgrade-state.json.gz` is an `anvil_dumpState` snapshot of a Hoodi fork **with core's EDF upgrade
applied**. `manifest.json` records the pinned fork block and the resulting addresses. Together they
let integration tests run against DSM v5 with contract guardians without re-running an eight-minute
upgrade per session (`tests/fixtures/edf.py`).

The fork URL is still required. An anvil dump contains only state the node *modified*, so the
upgrade's own deployments are in it while the untouched protocol underneath is not — the fork supplies
that base state. Nothing about the upgrade is re-executed.

## Making it fully offline (not done yet)

`anvil --init` can serve a self-contained genesis with no node at all, and `tests/fork_snapshot.py`
builds one by merging the base state from foundry's RPC cache with the upgrade dump on top. This has
been shown to work: DSM v5, guardians, delegates and `isMinDepositDistancePassed` all resolve with no
`--fork-url`. What it needs is a *complete* cache, and that is the fiddly part:

- The cache only holds what a fork actually fetched, and a read that was never warmed comes back as an
  empty account or a zero slot — surfacing later as `Panic 0x32: array index out of bounds` rather
  than anything that names the missing state.
- Most of the base state is fetched by **the upgrade run itself**, not by the tests: with the dump
  loaded, test reads resolve locally and never touch the network. So the cache directory for the
  pinned block must **accumulate across both runs** — do not clear it between the upgrade and the
  suite, or the base state is lost.
- Capture order that should work: run the upgrade (populates base state) → run the full suite against
  `--fork-url` + `--load-state` (adds whatever the tests additionally read) → stop anvil with SIGTERM
  so the cache flushes (`kill -9` loses it) → `zstd -dc` the cache (foundry ≥1.7 compresses it, at
  `<block>/storage.json`) → `python -m tests.fork_snapshot <cache.json> <genesis.json> <dump.json>
  560048` → gzip.

Warming with less than the real suite produces a genesis that boots and serves the protocol but
panics on the first slot no one read during capture, which is a confusing failure to debug. That is
why this is not committed yet.

## Why not the already-deployed EDF

Hoodi has a `DelegationFactory` at `0x76Af23C7e71004038BeE4a1ceba8c441f4cA239b`, but it predates
core's source (it exposes `assignDelegate`, since renamed to `nominateDelegate`) and the chain it sits
on still runs **DSM v4**, where every delegation path in this bot is a deliberate no-op. Testing
against it would verify the old deployment and none of this work.

## Regenerating

Needed when core's EDF branch moves, or when the pinned block ages out of your RPC's history.

Prerequisites: an archive-capable Hoodi RPC, `just`, and **foundry v1.7.1** — the version pinned in
the EDF repo's `.foundryref`. Older foundry cannot resolve solc `=0.8.35` or the `osaka` evm version
that repo requires, and fails with `No solc version exists that matches the version requirement`:

```bash
foundryup --install v1.7.1
```

1. A core checkout on the EDF branch. A worktree keeps your own checkout untouched, and `node_modules`
   can be shared because that branch changes no dependencies:

   ```bash
   git -C /path/to/core fetch origin feat/edf
   git -C /path/to/core worktree add /tmp/core-edf origin/feat/edf
   ln -s /path/to/core/node_modules /tmp/core-edf/node_modules
   (cd /tmp/core-edf && yarn hardhat compile)
   ```

2. Fork Hoodi at a pinned block:

   ```bash
   BLOCK=$(( $(cast block-number --rpc-url "$HOODI_RPC") - 20 ))
   anvil --fork-url "$HOODI_RPC" --fork-block-number "$BLOCK" --port 8545 --silent &
   ```

3. Apply the upgrade — the same steps file core's own EDF integration job uses. Takes ~8 minutes and
   ends with a mock Aragon vote plus a scheduled proposal execution:

   ```bash
   cd /tmp/core-edf
   RPC_URL=http://127.0.0.1:8545 NETWORK=hoodi RUN_NETWORK=local MODE=forking UPGRADE=true \
     STEPS_FILE=upgrade/steps-edf-mock.json AUTO_CONFIRM=true ALLOW_SKIP_STEPS=true \
     HOLDER=0xc3c65cb7aa6d36f051f875708b8e17f9a0b210ed \
     yarn deploy:upgrade
   ```

   Confirm before continuing — the upgrade is only in effect once the proposal executed:

   ```bash
   DSM=$(cast call 0xe2EF9536DAAAEBFf5b1c130957AB3E80056b06D8 'depositSecurityModule()(address)' --rpc-url http://127.0.0.1:8545)
   cast call "$DSM" 'VERSION()(uint256)' --rpc-url http://127.0.0.1:8545   # must be 5
   ```

4. Dump, compress, and refresh the manifest. `anvil_dumpState` returns gzip-hex, so decode it first:

   ```bash
   cast rpc anvil_dumpState --rpc-url http://127.0.0.1:8545 \
     | tr -d '"' | sed 's/^0x//' | xxd -r -p | gzip -dc > upgrade-state.json
   gzip -9 -c upgrade-state.json > tests/fixtures/edf/upgrade-state.json.gz
   ```

   Then update `manifest.json`: `forkBlock`, `depositSecurityModule`, `delegationFactory` (read
   `delegationFactory.address` from core's `deployed-local.json`), `guardians` and
   `guardianDelegates`. `tests/fixtures/edf.py` asserts `dsmVersion` on startup, so a snapshot that
   failed to load fails the suite loudly instead of silently testing a v4 chain.

Guardian delegates in the snapshot are anvil dev accounts 1–7, so their keys are known and council
messages can be signed in tests. The bot uses account 0; accounts 8 and 9 are free for test-owned
delegation contracts.
