#!/usr/bin/env python
"""Ad-hoc harness for the LIP-37 guardian-delegate reverse mapping.

It stands up a local anvil, installs a minimal ``getDelegate()`` stub at a few guardian addresses
(via ``anvil_setCode``), and then drives the *real* production code paths against it:

    1. ``LidoContracts.get_guardian_delegates()`` — resolves every guardian's current delegate and
       builds the ``{delegate_EOA: guardian_contract}`` reverse map the Data Bus transport consumes.
    2. Reverse mapping — a Data Bus ``sender`` (delegate EOA) is resolved back to its guardian.
    3. Fail closed — a delegate is rotated on-chain; the stale delegate must stop resolving.

No external contract bytecode is required: the guardian stub is a hand-written runtime that returns a
constant address for any call, which is all ``getDelegate()`` needs here.

Usage:
    poetry run python scripts/adhoc_edf_reverse_mapping.py [--anvil-path /path/to/dir/] [--port 8546]

Requires ``anvil`` (Foundry) on PATH (or via --anvil-path).
"""

import argparse
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import cast
from unittest.mock import Mock

# Make ``src/`` importable when run as a plain script (pytest sets this via pyproject pythonpath).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from eth_typing import ChecksumAddress  # noqa: E402
from web3 import HTTPProvider, Web3  # noqa: E402
from web3.types import RPCEndpoint  # noqa: E402

from blockchain.contracts.guardian import GuardianContract  # noqa: E402
from blockchain.web3_extentions.lido_contracts import LidoContracts  # noqa: E402

# Deterministic guardian contract addresses and their initial delegate EOAs.
GUARDIAN_A = Web3.to_checksum_address('0xA000000000000000000000000000000000000001')
GUARDIAN_B = Web3.to_checksum_address('0xB000000000000000000000000000000000000002')
DELEGATE_A = Web3.to_checksum_address('0x1111111111111111111111111111111111111111')
DELEGATE_B = Web3.to_checksum_address('0x2222222222222222222222222222222222222222')
DELEGATE_A_ROTATED = Web3.to_checksum_address('0x3333333333333333333333333333333333333333')


def _delegate_stub_code(delegate: str) -> str:
    """Runtime bytecode that ABI-returns ``delegate`` (as an address) for ANY calldata.

    PUSH20 <addr>; PUSH1 0; MSTORE; PUSH1 32; PUSH1 0; RETURN
    MSTORE right-aligns the 20-byte address into a 32-byte word (12 zero bytes of left padding),
    which is exactly the ABI encoding of an address.
    """
    addr = bytes.fromhex(delegate[2:])
    code = bytes([0x73]) + addr + bytes([0x60, 0x00, 0x52, 0x60, 0x20, 0x60, 0x00, 0xF3])
    return '0x' + code.hex()


@contextmanager
def anvil(anvil_path: str, port: str):
    proc = subprocess.Popen(
        [f'{anvil_path}anvil', '-p', port, '--silent'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        w3 = Web3(HTTPProvider(f'http://127.0.0.1:{port}', request_kwargs={'timeout': 30}))
        for _ in range(50):
            if w3.is_connected():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError('anvil did not come up')
        yield w3
    finally:
        proc.terminate()
        proc.wait()


def _set_delegate(w3: Web3, guardian: ChecksumAddress, delegate: str) -> None:
    ok = w3.provider.make_request(RPCEndpoint('anvil_setCode'), [guardian, _delegate_stub_code(delegate)])
    assert 'error' not in ok, ok
    # Sanity: the real GuardianContract wrapper reads back what we installed.
    contract = cast(GuardianContract, w3.eth.contract(address=guardian, ContractFactoryClass=GuardianContract))
    assert Web3.to_checksum_address(contract.get_delegate()) == delegate


def _resolver(w3: Web3, guardians: list[ChecksumAddress]) -> LidoContracts:
    """A LidoContracts wired to the live anvil, with getGuardians() stubbed to `guardians`.

    Everything else — the guardian contract cache and getDelegate() calls — is the real code."""
    lido = LidoContracts.__new__(LidoContracts)
    lido.w3 = w3
    lido._guardian_cache = {}
    lido.deposit_security_module = Mock()
    lido.deposit_security_module.get_guardians = Mock(return_value=guardians)
    return lido


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--anvil-path', default=os.getenv('ANVIL_PATH', ''), help='dir containing the anvil binary (trailing slash)')
    parser.add_argument('--port', default='8546')
    args = parser.parse_args()

    with anvil(args.anvil_path, args.port) as w3:
        print(f'anvil up at 127.0.0.1:{args.port}, chain_id={w3.eth.chain_id}')

        # --- Install guardians with their initial delegates ---
        _set_delegate(w3, GUARDIAN_A, DELEGATE_A)
        _set_delegate(w3, GUARDIAN_B, DELEGATE_B)

        lido = _resolver(w3, [GUARDIAN_A, GUARDIAN_B])

        # 1) Resolve the reverse map using the production method.
        delegates = lido.get_guardian_delegates()
        print('resolved delegate map:', delegates)
        assert delegates == {DELEGATE_A: GUARDIAN_A, DELEGATE_B: GUARDIAN_B}, delegates

        # 2) Reverse map a Data Bus sender (delegate EOA) back to its guardian.
        sender = DELEGATE_B
        assert delegates.get(sender) == GUARDIAN_B
        print(f'sender {sender} -> guardian {delegates[sender]}')

        # 3) Fail closed: rotate guardian A's delegate; the old delegate must stop resolving.
        _set_delegate(w3, GUARDIAN_A, DELEGATE_A_ROTATED)
        delegates_after = lido.get_guardian_delegates()
        print('delegate map after rotation:', delegates_after)
        assert DELEGATE_A not in delegates_after, 'stale delegate still resolves — NOT fail-closed'
        assert delegates_after[DELEGATE_A_ROTATED] == GUARDIAN_A

        print('\nOK: reverse mapping and fail-closed rotation behave as expected.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
