"""Turn a warmed foundry fork cache into a self-contained anvil genesis.

Integration tests fork a testnet through `tests.fork.anvil_fork`, which needs a reachable (and for a
pinned block, archive) RPC on every run. This module removes that dependency: fork once against a
live node, then convert what the fork actually fetched into a genesis file that `anvil --init` can
serve with no upstream node.

    # once, with an RPC reachable — exercise the flows the tests need so their reads get cached
    anvil --fork-url $RPC --fork-block-number $N ...   # run the suite against it, then stop anvil
    python -m tests.fork_snapshot ~/.foundry/cache/rpc/hoodi/$N/storage.json snapshot.json 560048

    # from then on, offline
    anvil --init snapshot.json

The cache holds only accounts and slots the fork actually read. Anything a later test touches for
the first time comes back as an empty account or a zero slot instead of being fetched — silently.
So the warm-up run must cover the same reads, and `assert_snapshot_usable` should gate the suite so
an incomplete snapshot fails loudly rather than producing nonsense.
"""

import json
import sys
from typing import Any

CHAIN_ID_HOODI = 560048


def _code_hex(code_field: Any) -> str:
    """Flatten revm's tagged Bytecode enum into plain hex.

    Two variants show up in a testnet cache:

    - ``LegacyAnalyzed``: ``{bytecode, original_len, jump_table}``. ``bytecode`` carries 33 bytes of
      jumpdest-analysis padding, so it has to be truncated back to ``original_len`` — otherwise every
      contract's code hash is wrong, and anything reading EXTCODEHASH misbehaves.
    - ``Eip7702``: ``{delegated_address, version, raw}``, where ``raw`` is the 23-byte delegation
      designator. anvil's dev accounts carry these on public testnets, since their keys are public.
    """
    if code_field is None:
        return '0x'
    if isinstance(code_field, str):
        return code_field

    variant, inner = next(iter(code_field.items()))
    if isinstance(inner, str):
        return inner
    if variant == 'Eip7702':
        # Serialised two ways depending on the foundry version: older builds carry the designator as
        # `raw`, newer ones only the target, in which case it has to be rebuilt — a 7702 designator is
        # the magic `0xef0100` followed by the 20-byte address.
        if 'raw' in inner:
            return inner['raw']
        return '0xef0100' + inner['delegated_address'][2:]

    raw = inner.get('bytecode') or inner.get('raw') or '0x'
    original_len = inner.get('original_len')
    if original_len is None:
        return raw
    return '0x' + raw[2:][: original_len * 2]


def _pad32(value: str) -> str:
    """Widen a cache value to a full 32-byte word.

    The cache stores slots unpadded — an address-valued slot comes back as 20 bytes — while genesis
    storage is a fixed 32-byte map. Without this the slot reads as a much smaller number.
    """
    return '0x' + value[2:].rjust(64, '0')


def _hex(value: Any) -> str:
    return hex(value) if isinstance(value, int) else value


def merge_dump(genesis: dict, dump: dict) -> dict:
    """Overlay `anvil_dumpState` output onto a genesis built from the RPC cache.

    Both halves are needed and neither is sufficient. The RPC cache holds base chain state that was
    *fetched* from the upstream node; a dump holds state the node *modified* locally. So after running
    an upgrade on a fork, everything the upgrade deployed or wrote — new DSM, re-pointed locator,
    delegation contracts — exists only in the dump, while the untouched protocol it builds on exists
    only in the cache.

    Merged per slot rather than per account: a dump carries only the slots it changed, so replacing an
    account wholesale would drop every cached slot the upgrade did not touch (for a proxy, that means
    losing everything except the implementation pointer).

    The dump's block environment wins, since it describes the chain *after* the upgrade — including any
    time the migration advanced to pass voting delays.
    """
    accounts = dict(genesis['alloc'])
    for addr, account in dump.get('accounts', {}).items():
        key = addr.lower()
        existing = accounts.get(key, {})
        storage = dict(existing.get('storage', {}))
        storage.update({_pad32(slot): _pad32(value) for slot, value in account.get('storage', {}).items()})

        merged = {
            'balance': account.get('balance', existing.get('balance', '0x0')),
            'nonce': _hex(account.get('nonce', existing.get('nonce', 0))),
        }
        code = _code_hex(account.get('code')) if account.get('code') is not None else existing.get('code', '0x')
        if code != '0x':
            merged['code'] = code
        if storage:
            merged['storage'] = storage
        accounts[key] = merged

    block = dump.get('block')
    if block:
        genesis = {**genesis, 'number': block['number'], 'timestamp': block['timestamp']}
        for src, dst in (('gas_limit', 'gasLimit'), ('basefee', 'baseFeePerGas')):
            if block.get(src) is not None:
                genesis[dst] = _hex(block[src])

    return {**genesis, 'alloc': accounts}


def cache_to_genesis(cache: dict, chain_id: int = CHAIN_ID_HOODI) -> dict:
    """Build a geth-style genesis that starts at the forked block with the forked state.

    Genesis rather than ``anvil --load-state``: a load-state snapshot carries no block bodies, so
    anvil can only serve it with the height rebased to 0, and height 0 breaks every contract that
    subtracts a stored block number — ``DSM.isMinDepositDistancePassed`` computes
    ``block.number - lastDepositBlock``, which underflows and reverts. A genesis declares its own
    starting height, so the chain begins *at* the forked block and those subtractions stay in range.
    """
    env = cache['meta']['block_env']
    storage = {addr.lower(): slots for addr, slots in cache.get('storage', {}).items()}

    alloc: dict[str, dict] = {}
    for addr, account in cache['accounts'].items():
        key = addr.lower()
        entry: dict[str, Any] = {'balance': account['balance'], 'nonce': _hex(account['nonce'])}
        code = _code_hex(account.get('code'))
        if code != '0x':
            entry['code'] = code
        slots = storage.get(key)
        if slots:
            entry['storage'] = {_pad32(slot): _pad32(value) for slot, value in slots.items()}
        alloc[key] = entry

    return {
        'config': {
            'chainId': chain_id,
            'homesteadBlock': 0,
            'eip150Block': 0,
            'eip155Block': 0,
            'eip158Block': 0,
            'byzantiumBlock': 0,
            'constantinopleBlock': 0,
            'petersburgBlock': 0,
            'istanbulBlock': 0,
            'berlinBlock': 0,
            'londonBlock': 0,
            'shanghaiTime': 0,
            'cancunTime': 0,
            'pragueTime': 0,
        },
        'number': env['number'],
        # Kept from the fork, not reset: beacon-root reads are keyed by timestamp, and the EIP-4788
        # ring buffer in the snapshot only lines up with the forked timestamps.
        'timestamp': env['timestamp'],
        'gasLimit': _hex(env['gas_limit']),
        'baseFeePerGas': _hex(env['basefee']),
        'difficulty': '0x0',
        'mixHash': env.get('prevrandao') or '0x' + '00' * 32,
        'coinbase': env.get('beneficiary') or '0x' + '00' * 20,
        'extraData': '0x',
        'alloc': alloc,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(f'usage: python -m tests.fork_snapshot <cache.json> <genesis.json> [dump.json] [chain_id={CHAIN_ID_HOODI}]')
        return 2

    src, dst = argv[1], argv[2]
    dump_path = argv[3] if len(argv) > 3 and argv[3] != '-' else None
    chain_id = int(argv[4]) if len(argv) > 4 else CHAIN_ID_HOODI
    with open(src) as fh:
        cache = json.load(fh)

    genesis = cache_to_genesis(cache, chain_id)
    if dump_path:
        with open(dump_path) as fh:
            genesis = merge_dump(genesis, json.load(fh))
    with open(dst, 'w') as fh:
        json.dump(genesis, fh)

    with_code = sum(1 for account in genesis['alloc'].values() if 'code' in account)
    slots = sum(len(account.get('storage', {})) for account in genesis['alloc'].values())
    print(f'number={genesis["number"]} accounts={len(genesis["alloc"])} with_code={with_code} storage_slots={slots}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
