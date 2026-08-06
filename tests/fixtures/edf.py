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

# anvil's deterministic dev keys, by address. The snapshot's guardian delegates are drawn from these,
# which is what makes signing as a council delegate possible at all — the addresses come out of the
# upgrade's parameters, so the map is needed to get from a guardian's delegate back to its key.
ANVIL_KEYS = {
    '0x70997970C51812dc3A010C7d01b50e0d17dc79C8': '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d',
    '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC': '0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a',
    '0x90F79bf6EB2c4f870365E785982E1f101E93b906': '0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6',
    '0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65': '0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a',
    '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc': '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba',
    '0x976EA74026E726554dB657fA54763abd0C3a0aa9': '0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e',
    '0x14dC79964da2C08b23698B3D3cc7Ca32193d9955': '0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356',
}


def _clear_delegate_code(w3, manifest: dict) -> None:
    """Make the guardians' delegates plain EOAs, as real delegates are.

    The upgrade's parameters point the delegates at anvil's dev accounts, and on a public testnet those
    keys are public — someone has set EIP-7702 delegations on all of them, so each carries a 23-byte
    `ef0100…` designator. That breaks DSM v5 signature verification for a reason worth knowing:
    OpenZeppelin's SignatureChecker treats any address with code as a contract, so instead of
    recovering the signature it calls ERC-1271 `isValidSignature` on the 7702 target, which does not
    implement it — and a correctly signed council message is rejected as InvalidSignature.

    Clearing the code models a delegate whose key is not public. It also documents a live constraint:
    a guardian delegate must not carry a 7702 delegation unless its target implements ERC-1271.
    """
    for delegate in {Web3.to_checksum_address(address) for address in manifest['guardianDelegates'].values()}:
        if w3.eth.get_code(delegate):
            w3.provider.make_request('anvil_setCode', [delegate, '0x'])


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
        _clear_delegate_code(w3, edf_manifest)
        yield w3

    variables.LIDO_LOCATOR = previous_locator


@pytest.fixture
def web3_edf(web3_edf_session):
    """Per-test isolation on the shared node: everything a test writes is rolled back."""
    snapshot = web3_edf_session.provider.make_request('evm_snapshot', [])['result']
    yield web3_edf_session
    web3_edf_session.provider.make_request('evm_revert', [snapshot])
