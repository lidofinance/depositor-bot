"""Fixtures for a chain with core's EDF / DSM v5 upgrade applied.

The chain is produced once, out of band, by running core's own upgrade against a forked testnet
(`lidofinance/core@feat/edf`, `MODE=forking NETWORK=hoodi UPGRADE=true
STEPS_FILE=upgrade/steps-edf-mock.json`) and dumping the result with `anvil_dumpState`. That dump is
committed as `edf/upgrade-state.json.gz` and replayed here with `anvil --load-state`, so tests get
DSM v5 and contract guardians without re-running an eight-minute upgrade.

Why the fork URL is still needed: an anvil dump contains only state the node *modified*, so the
upgrade's own deployments are in it but the untouched protocol underneath is not. The fork supplies
that base state; nothing about the upgrade is re-executed.

The node is session-scoped and each test is wrapped in evm_snapshot/evm_revert, so tests can deploy
and grant roles freely without leaking into each other.
"""

import gzip
import json
import os
import shutil
from pathlib import Path

import pytest
from web3 import HTTPProvider

import variables
from blockchain.typings import Web3
from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.transaction import TransactionUtils
from tests.fork import anvil_fork

EDF_DIR = Path(__file__).parent / 'edf'
EDF_PORT = '8555'

# anvil dev accounts 1..7 are the guardians' delegates in the snapshot, so the bot uses account 0 and
# the tests own 8 and 9. A delegation contract rejects owner == delegate (OwnerCannotBeDelegate).
BOT_ACCOUNT_PK = '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'  # account 0
DELEGATION_OWNER = '0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f'  # account 8
SPARE_DELEGATE = '0xa0Ee7A142d267C1f36714E4a8F75612F20a79720'  # account 9


@pytest.fixture(scope='session')
def edf_manifest() -> dict:
    """Addresses and the pinned fork block for the snapshot, recorded when it was generated."""
    return json.loads((EDF_DIR / 'manifest.json').read_text())


@pytest.fixture(scope='session')
def edf_state_file(tmp_path_factory) -> str:
    """Decompress the committed snapshot; anvil's --load-state wants plain JSON."""
    destination = tmp_path_factory.mktemp('edf') / 'upgrade-state.json'
    with gzip.open(EDF_DIR / 'upgrade-state.json.gz', 'rb') as source, open(destination, 'wb') as target:
        shutil.copyfileobj(source, target)
    return str(destination)


@pytest.fixture(scope='session')
def web3_edf_session(edf_manifest, edf_state_file):
    """One upgraded node for the whole session."""
    rpc_endpoint = variables.WEB3_RPC_ENDPOINTS[0] if variables.WEB3_RPC_ENDPOINTS else ''
    previous_locator = variables.LIDO_LOCATOR
    # LidoContracts resolves everything from the locator, so it has to match the snapshot's chain.
    variables.LIDO_LOCATOR = Web3.to_checksum_address(edf_manifest['lidoLocator'])

    with anvil_fork(
        os.getenv('ANVIL_PATH', ''),
        rpc_endpoint,
        edf_manifest['forkBlock'],
        port=EDF_PORT,
        load_state=edf_state_file,
        # Mine on demand: these tests only send transactions and read them back, and a fixed block
        # interval would make every send wait for the next block.
        block_time=None,
    ):
        w3 = Web3(HTTPProvider(f'http://127.0.0.1:{EDF_PORT}', request_kwargs={'timeout': 3600}))
        assert w3.is_connected(), 'Failed to connect to the EDF fork.'
        w3.attach_modules({'transaction': TransactionUtils, 'lido': LidoContracts})

        expected = edf_manifest['dsmVersion']
        assert w3.lido.dsm_version == expected, (
            f'EDF snapshot did not load: DSM version is {w3.lido.dsm_version}, expected {expected}. '
            'Regenerate tests/fixtures/edf/upgrade-state.json.gz.'
        )
        yield w3

    variables.LIDO_LOCATOR = previous_locator


@pytest.fixture
def web3_edf(web3_edf_session):
    """Per-test isolation on the shared node: everything a test writes is rolled back."""
    snapshot = web3_edf_session.provider.make_request('evm_snapshot', [])['result']
    yield web3_edf_session
    web3_edf_session.provider.make_request('evm_revert', [snapshot])
