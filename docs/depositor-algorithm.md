# Depositor bot algorithm

This document describes the per-iteration logic of `DepositorBot.execute()`.
The implementation lives in `src/bots/depositor.py`.

## How `execute()` is driven

The bot runs in a loop for as long as the process is alive (`Executor`,
`src/blockchain/executor.py`): it waits for the next scheduled block, calls
`bot.execute(block)` (which checks balances and then runs the deposit algorithm),
and the bool that `execute` returns sets when it runs next:
- `True` → schedule `BLOCKS_BETWEEN_EXECUTION` blocks ahead (we acted, or hit a
  wait that won't clear soon — back off);
- `False` → run again on the very next block (keep polling).


## Step 1 — Check balances

**What it does.** Every run starts by refreshing balance metrics: how much ETH
the bot's own account holds and how much each guardian holds. This is
monitoring only — it never blocks a deposit or top-up.

**How.** `_check_balance()`:
- If an account is configured, read its balance and write it to the
  `ACCOUNT_BALANCE` metric.
- Read the guardian list from the DSM (`get_guardians()`), then read each
  guardian's balance on every connected provider (the main RPC, plus the
  on-chain-transport RPC when that transport is enabled) and write them to the
  `GUARDIAN_BALANCE` metric.

**Why.** These numbers feed monitoring/alerting so operators notice a drained
bot account or an under-funded guardian early. They take no part in any
deposit/top-up decision.

## Step 2 — Main algorithm (`_execute_actual`)

**What it does.** The core of the bot: figure out which module needs ETH and try
to deposit or top it up. It runs right after `_check_balance()` and returns the
bool value that `execute()` hands back to the Executor.

**How.** First it refreshes what the bot knows about each module, then it runs a
few must-pass checks (and exits early if any fails), reads the allocation it will
reuse later, and finally hands off to the two phases.

1. **Refresh module state.** For every whitelisted module we look up whether it
   has a guardian quorum right now; if it does, we stamp "now" as that module's
   last heartbeat — this is what the retention window later measures against. We
   also run a gas-price probe, but only to publish a metric. Nothing here blocks
   anything: gas and quorum are checked again later, where they actually matter.
   Method: `_refresh_modules_state()`.

2. **Must-pass checks — exit early if any fails.** A deposit or top-up can only
   happen if all of these hold, so we check them up front and stop the whole
   iteration the moment one is missing:
   - non-zero depositable ether — `lido.get_depositable_ether() != 0`;
   - the protocol allows deposits and a guardian quorum is configured: `lido.can_deposit()` and
     `dsm.get_guardian_quorum() != 0`.
   On any miss we return `False`, and the Executor just retries on the next block
   (no back-off), so the bot resumes the moment the state recovers.

3. **Note whether deposits are paused.** We read the DSM pause flag once —
   `dsm.is_deposits_paused()`. Pausing stops deposits but not top-ups, so we
   don't exit here: we just remember the flag and use it to skip deposit
   candidates this iteration while top-ups keep flowing.

4. **Read the allocation once.** We ask the StakingRouter how the buffered ETH
   would spread across modules — the seed allocation, via
   `getDepositAllocations(eth, is_top_up=False)`. We compute it a single time
   here and reuse it in both phases to pick and order candidates: phase A for
   seed deposits to `0x02` modules, phase B for full deposits to `0x01` modules.
   (Phase B additionally computes a top-up variant when top-up is enabled.)

5. **Phase A — seed deposits to `0x02` modules** (`_phase_seed`)
     Only `0x02` candidates, only while the DSM is not paused.
     - collect candidates: whitelisted, active, non-zero seed allocation;
     - sort ascending by stake;
     - go through candidates; the first one that isn't "stale" decides the outcome
       and stops the phase:
       - distance not passed → wait, stop;
       - quorum ready → deposit (gas + quorum re-checked before send), stop;
       - quorum on cooldown → wait next block, stop;
       - no quorum for a while (stale) → try the next candidate;
     - no candidate acted → fall through to phase B.

6. **Phase B — full `0x01` deposits, plus top-ups to `0x02`** (`_phase_full` / `_phase_full_and_topup`)
     Full `0x01` deposits, plus `0x02` top-ups when top-ups are on
     (`ENABLE_TOP_UP` and the TopUpGateway not paused). Top-ups off → `0x01` only;
     top-ups off and deposits paused → nothing to do.
     - collect candidates: `0x01` from seed allocation (skipped while deposits
       paused), `0x02` from top-up allocation; each whitelisted, active, non-zero
       allocation;
     - merge both types, sort ascending by stake;
     - go through candidates; the first one that isn't "stale" decides the outcome
       and stops the phase:
       - `0x01` → same as phase A (distance → quorum: deposit / cooldown wait / stale → next);
       - `0x02` top-up → no quorum needed; top-up distance not passed → wait, stop;
         else top-up, stop (a top-up never goes "stale", so it never tries the next candidate);
     - no candidate acted → iteration ends, retry on the next block.


## Deposit into a module (`_deposit_to_module`)

Runs the final gas and quorum checks for one module, then builds and sends the
deposit transaction.
- pick the strategy: CSM module → CSM strategy, otherwise the default one
  (`_select_strategy`) — they differ only in the gas rule;
- gas check — `strategy.is_gas_price_ok(module_id)`; too high → stop, no deposit
  (there is no keys-count check anymore);
- quorum re-check — read the quorum again (`_get_quorum`); if it is no longer
  there → stop;
- build & send — `prepare_and_send_tx`: sort the guardian signatures by address,
  build the `depositBufferedEther` tx, dry-run it locally (`transaction.check`),
  then send it (via the private/flashbots relay if configured, otherwise a normal
  broadcast);
- return whether the tx made it on-chain.

 ## Top up a module (`_top_up_to_module`)

  Runs the checks for one `0x02` module and sends the top-up. No guardian quorum is
  involved — only the bot can call top-up.
  - pick the strategy by module type — `CMv2TopUpStrategy` for `curated-onchain-v2`;
    unknown type → stop;
  - gas check — `strategy.is_gas_price_ok()`; too high → stop;
  - cap the batch — `max_validators = min(MAX_VALIDATORS_PER_TOP_UP,
    topup_gateway.get_max_validators_per_top_up())`;
  - pick which validators to top up — `get_topup_candidates(...)` (below); none → stop;
  - build & send — `topup_gateway.top_up(module_id, proof_data)`, dry-run locally
    (`transaction.check`), then send without the private relay
    (`transaction.send(..., use_relay=False)`);
  - return whether the tx made it on-chain.

  ### Selecting validators (`get_topup_candidates`, CMv2)

  Turns the module's top-up allocation into a concrete list of validators and their proofs:
  - split the allocation across operators — `cmv2.get_deposits_allocation`; nothing
    allocated → stop;
  - fetch those operators' used keys from the Keys API;
  - sync the consolidation index up to the finalized block (before the heavy load);
    if it fails → skip the top-up, so we never risk topping up a consolidating key;
  - load the beacon state for these keys (anchors the proof slot — the heavy step):
    gives each validator's index, balance and pending deposits;
  - read the set of keys in pending ConsolidationBus requests (to exclude them);
  - read the top-up balance limits from the gateway (target balance, min top-up);
    a validator is eligible only up to `target − min`;
  - per operator, keep validators that are: not in a pending consolidation (as source
    or target), present in the state, active, not slashed, not exiting, not a
    consolidation target, and below the eligible balance cap; take them in order until
    the operator's allocation runs out (never leaving a below-minimum top-up);
  - sort all candidates by validator index (the gateway requires strictly ascending),
    cap to `max_validators`, and build the SSZ proofs (`build_topup_proofs`).
