# Depositor bot algorithm

This document describes the per-iteration logic of `DepositorBot.execute()`.
The implementation lives in `src/bots/depositor.py`; this is the authoritative
spec the implementation follows.

## Glossary

- **wc_type** — the withdrawal-credentials type of a staking module:
  `0x01` = full-deposit (32 ETH) modules; `0x02` = top-up modules.
- **seed allocation** — `getDepositAllocations(eth, is_top_up=False)`. The
  baseline allocation of buffered ETH across modules, used by both phases for
  candidate selection and ordering.
- **top-up allocation** — `getDepositAllocations(eth, is_top_up=True)`. Takes
  per-module top-up capacity into account; only computed when phase B with
  `ENABLE_TOP_UP=True` actually runs.
- **stake** — sort key for candidates: `new_allocations[i] - allocated[i]`.
  Lower stake → higher priority (we feed underfunded modules first).
- **quorum-retention cooldown** — `now - last_heart_beat <= QUORUM_RETENTION_MINUTES`.
  Records when a module last had a guardian quorum; protects against premature
  fall-through when council messages are simply late.

---

## Step 0 — Preparation (before module selection)

1. `_check_balance()` — refresh account / guardian balance metrics.
2. For each module in `DEPOSIT_MODULES_WHITELIST`:
   - call `_get_quorum(module_id)` (also refreshes `_module_last_heart_beat`);
   - call `_select_strategy(module_id).is_gas_price_ok(module_id)` — **for
     metrics only**, never as a gate.

Neither call gates execution at this stage; gas and quorum are re-checked at
the points where they actually matter (`_deposit_to_module`, phase iteration).

## Step 1 — `execute()`

- Call `_execute_actual()`.

(There is no legacy `_execute_legacy` branch in the current code; all
StakingRouter versions in scope are v4+.)

## Step 2 — `_execute_actual()` dispatcher

- Run **phase A**.
  - Phase A returned `(True, success)` → return `success`. We deposited (or
    tried and hit gas/quorum guards) — done for this iteration.
  - Phase A returned `(True, False)` with reason = **cooldown** → end the
    bot iteration. Do **not** fall through to phase B; we wait for the next
    bot tick to give the council more time.
  - Phase A returned `(False, False)` (no candidates) → continue to phase B.
- Run **phase B** with the same `(done, success)` semantics:
  - success → end; cooldown → end; empty → end.

Both phases share the same return contract:

```
done = True   →  caller stops this iteration (we acted or hit cooldown)
done = False  →  phase produced nothing; caller continues to the next phase
```

## Step 3 — Phase A — seed deposits into 0x02 modules

1. `depositable_ether = lido.get_depositable_ether()`.
   - If `0` → nothing to do this iteration, return `False` immediately. (The
     buffer is empty; even top-ups have nothing to draw against.)
2. `seed_allocated, seed_new = getDepositAllocations(eth, is_top_up=False)`.
   Result is computed once in `_execute_actual` and **forwarded to phase B**
   so it doesn't recompute.
3. Stream candidates while iterating the module digests (no separate list +
   second pass):
   - `wc_type == 2`
   - module in `DEPOSIT_MODULES_WHITELIST`
   - `seed_allocated[i] > 0`
4. Sort candidates by `stake = seed_new[i] - seed_allocated[i]` ascending.
5. Iterate:
   - `canDeposit(module_id) == False` → `next`.
   - Quorum available right now (`_get_quorum(module_id) is not None`)?
     - **Yes** → `_deposit_to_module(module_id)` (gas check + send happen
       inside). Return its result; **stop iterating modules**.
     - **No** → cooldown active (`now - last_heart_beat <= QUORUM_RETENTION_MINUTES`)?
       - **Yes** → exit phase A with reason "cooldown". Phase B is **not**
         entered; we wait for the next bot tick.
       - **No** → `next`.
6. If candidates exhaust without acting → phase A is empty, fall through to
   phase B.

## Step 4 — Phase B

### B.0 — `ENABLE_TOP_UP == False`

1. Reuse `seed_allocated`, `seed_new` from step 3.2 (computed in
   `_execute_actual`).
2. Candidates: `wc_type == 1`, module in whitelist, `seed_allocated[i] > 0`.
3. Sort by `stake = seed_new[i] - seed_allocated[i]` and iterate exactly as
   in step 3.5 (`canDeposit → quorum-now → cooldown → next/stop/deposit`).
4. End.

### B.1 — `ENABLE_TOP_UP == True`

1. `topup_allocated, topup_new = getDepositAllocations(eth, is_top_up=True)`
   (this variant factors in per-module top-up capacity).
2. Candidates: module in whitelist, with per-type allocation filter:
   - `wc_type == 2` → requires `topup_allocated[i] > 0`.
   - `wc_type == 1` → requires `seed_allocated[i] > 0` (full deposits draw
     from the seed allocation, not the top-up one).
3. Sort key: `stake` per type:
   - 0x02: `topup_new[i] - topup_allocated[i]`.
   - 0x01: `seed_new[i] - seed_allocated[i]`.
4. Iterate:
   - **0x02 candidate (top-up):**
     - `topup_gateway.can_top_up(module_id)` False → `next`.
     - `topup_gateway.is_block_distance_passed(module_id)` (new method; while
       the contract is not yet deployed it returns `True` and logs a warning):
       - **False** → exit phase B, wait for the next bot tick.
       - **True** → `_top_up_to_module(module_id, module_address,
         module_allocation = topup_allocated[i])`. Return its result; **stop
         iterating**.
   - **0x01 candidate (full deposit):**
     - `canDeposit(module_id)` False → `next`.
     - Quorum available right now?
       - **Yes** → `_deposit_to_module(module_id)` (gas check + send inside).
         The deposit itself doesn't take an allocation parameter — the DSM
         contract decides the deposit count from current chain state. Return
         its result; **stop iterating**.
       - **No** → cooldown active?
         - **Yes** → exit phase B, wait for the next bot tick.
         - **No** → `next`.
5. End of iteration — if nothing acted, return `(False, False)` to the
   dispatcher.

## Step 5 — `_deposit_to_module(module_id)`

1. `gas_ok = strategy.is_gas_price_ok(module_id)`. No keys-count check —
   `can_deposit_keys_based_on_*` is gone and there is no separate
   keys-amount branch.
2. If `gas_ok` is `False` → return `False`.
3. Collect the quorum, call `prepare_and_send_tx(module_id, quorum)`.
4. Return the result.

(A defensive quorum re-check between steps 2 and 3 guards against the rare
case where the quorum disappears mid-iteration.)

## Step 6 — `_top_up_to_module(module_id, module_address, module_allocation)`

1. Select a strategy by module type (`CMv2TopUpStrategy` for
   `curated-onchain-v2`); unknown type → return `False`.
2. `gas_ok = strategy.is_gas_price_ok()` — no keys-count check. If `False`
   → return `False`.
3. `max_validators = min(MAX_VALIDATORS_PER_TOP_UP,
   topup_gateway.get_max_validators_per_top_up())`.
4. `proof_data = strategy.get_topup_candidates(..., module_allocation,
   max_validators)`. The allocation is **forwarded**, not recomputed via
   `getDepositAllocations`.
5. If `proof_data` is empty → return `False`.
6. `topup_gateway.top_up(module_id, proof_data)` → `transaction.check` →
   `transaction.send`. Return the result.
