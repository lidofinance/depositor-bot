"""Fixtures for a chain with core's EDF / DSM v5 upgrade, forked from Hoodi.

Hoodi carries the EDF deployment, so the chain is a plain fork — everything is resolved through the
locator at fork time rather than from a committed snapshot.

What the fork does not supply is a *signing* delegate: the guardians' delegates on Hoodi are real
council keys. `edf_manifest` therefore rotates every guardian onto an anvil dev account whose key is
known, which is what makes signing a council message possible at all. Rotation is a nomination plus
`getCooldown()` seconds, so the session jumps the clock once.

The node is session-scoped and each test is wrapped in evm_snapshot/evm_revert, so tests can deploy
and grant roles freely without leaking into each other.
"""

import os

import pytest
from web3 import HTTPProvider

import variables
from blockchain.typings import Web3
from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.transaction import TransactionUtils
from tests.fork import anvil_fork

EDF_PORT = '8555'

# Hoodi's EDF locator. The default in variables.py is mainnet's and has no code here.
HOODI_EDF_LOCATOR = '0xe2EF9536DAAAEBFf5b1c130957AB3E80056b06D8'
# Predates core's source (its contracts expose `assignDelegate`, not `nominateDelegate`), which is why
# _nominate_delegate picks the name out of the bytecode. Still the only DelegationFactory on Hoodi.
HOODI_DELEGATION_FACTORY = '0x76Af23C7e71004038BeE4a1ceba8c441f4cA239b'
DSM_VERSION = 5

# Accounts 1..7 become the guardians' delegates, so the bot uses account 0 and the tests own 8 and 9.
# A delegation contract rejects owner == delegate (OwnerCannotBeDelegate).
BOT_ACCOUNT_PK = '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'  # account 0
DELEGATION_OWNER = '0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f'  # account 8
SPARE_DELEGATE = '0xa0Ee7A142d267C1f36714E4a8F75612F20a79720'  # account 9

# anvil's deterministic dev keys, by address — the pool guardians are rotated onto.
ANVIL_KEYS = {
    '0x70997970C51812dc3A010C7d01b50e0d17dc79C8': '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d',
    '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC': '0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a',
    '0x90F79bf6EB2c4f870365E785982E1f101E93b906': '0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6',
    '0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65': '0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a',
    '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc': '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba',
    '0x976EA74026E726554dB657fA54763abd0C3a0aa9': '0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e',
    '0x14dC79964da2C08b23698B3D3cc7Ca32193d9955': '0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356',
}

GUARDIAN_ABI = [
    {'name': 'getDelegate', 'type': 'function', 'stateMutability': 'view', 'inputs': [], 'outputs': [{'type': 'address'}]},
    {'name': 'getCooldown', 'type': 'function', 'stateMutability': 'view', 'inputs': [], 'outputs': [{'type': 'uint256'}]},
    {'name': 'owner', 'type': 'function', 'stateMutability': 'view', 'inputs': [], 'outputs': [{'type': 'address'}]},
    {
        'name': 'nominateDelegate',
        'type': 'function',
        'stateMutability': 'nonpayable',
        'inputs': [{'name': 'delegate', 'type': 'address'}],
        'outputs': [],
    },
]


def _guardian(w3, address: str):
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=GUARDIAN_ABI)


def _make_plain_eoa(w3, address: str) -> None:
    """Strip any EIP-7702 designator from a delegate-to-be.

    anvil's dev keys are public, so on a public testnet someone has set 7702 delegations on all of
    them. That breaks DSM v5 verification: OpenZeppelin's SignatureChecker treats any address with
    code as a contract and calls ERC-1271 on the 7702 target instead of recovering the signature, so
    a correctly signed council message is rejected as InvalidSignature. It also documents a live
    constraint — a guardian delegate must not carry a 7702 delegation unless its target implements
    ERC-1271.
    """
    if w3.eth.get_code(Web3.to_checksum_address(address)):
        w3.provider.make_request('anvil_setCode', [Web3.to_checksum_address(address), '0x'])


def _rotate_delegates(w3, guardians: list[str]) -> dict[str, str]:
    """Point every guardian at an anvil dev account and return {guardian: delegate}."""
    pool = list(ANVIL_KEYS)
    assert len(guardians) <= len(pool), f'{len(guardians)} guardians but only {len(pool)} known keys'

    assigned = {}
    cooldown = 0
    for guardian, delegate in zip(guardians, pool, strict=False):
        contract = _guardian(w3, guardian)
        owner = contract.functions.owner().call()
        w3.provider.make_request('anvil_impersonateAccount', [owner])
        w3.provider.make_request('anvil_setBalance', [owner, '0x56BC75E2D63100000'])
        _make_plain_eoa(w3, delegate)
        w3.eth.wait_for_transaction_receipt(
            contract.functions.nominateDelegate(Web3.to_checksum_address(delegate)).transact({'from': owner})
        )
        cooldown = max(cooldown, contract.functions.getCooldown().call())
        assigned[Web3.to_checksum_address(guardian)] = Web3.to_checksum_address(delegate)

    # A nomination only becomes the delegate after the contract's cooldown.
    w3.provider.make_request('evm_increaseTime', [cooldown + 1])
    w3.provider.make_request('evm_mine', [])

    for guardian, delegate in assigned.items():
        active = _guardian(w3, guardian).functions.getDelegate().call()
        assert active == delegate, f'{guardian} delegate is {active}, expected {delegate}'
    return assigned


@pytest.fixture(scope='session')
def web3_edf_session():
    """One forked node for the whole session, with every guardian rotated onto a known key."""
    previous_locator = variables.LIDO_LOCATOR
    variables.LIDO_LOCATOR = Web3.to_checksum_address(HOODI_EDF_LOCATOR)

    fork = anvil_fork(
        os.getenv('ANVIL_PATH', ''),
        fork_url=variables.WEB3_RPC_ENDPOINTS[0] if variables.WEB3_RPC_ENDPOINTS else None,
        port=EDF_PORT,
        # Mine on demand: these tests only send transactions and read them back, and a fixed block
        # interval would make every send wait for the next block.
        block_time=None,
    )
    fork.__enter__()
    try:
        w3 = Web3(HTTPProvider(f'http://127.0.0.1:{EDF_PORT}', request_kwargs={'timeout': 3600}))
        assert w3.is_connected(), 'Failed to connect to the EDF fork.'
        w3.attach_modules({'transaction': TransactionUtils, 'lido': LidoContracts})

        assert w3.lido.dsm_version == DSM_VERSION, f'Forked chain is not EDF: DSM version is {w3.lido.dsm_version}, expected {DSM_VERSION}.'
        w3.edf_guardian_delegates = _rotate_delegates(w3, w3.lido.deposit_security_module.get_guardians())
        yield w3
    finally:
        fork.__exit__(None, None, None)
        variables.LIDO_LOCATOR = previous_locator


@pytest.fixture(scope='session')
def edf_manifest(web3_edf_session) -> dict:
    """Chain facts the tests need, resolved from the fork instead of a committed snapshot."""
    return {
        'lidoLocator': HOODI_EDF_LOCATOR,
        'depositSecurityModule': web3_edf_session.lido.deposit_security_module.address,
        'dsmVersion': DSM_VERSION,
        'delegationFactory': HOODI_DELEGATION_FACTORY,
        'guardians': list(web3_edf_session.edf_guardian_delegates),
        'guardianDelegates': dict(web3_edf_session.edf_guardian_delegates),
    }


@pytest.fixture
def web3_edf(web3_edf_session):
    """Per-test isolation on the shared node: everything a test writes is rolled back."""
    snapshot = web3_edf_session.provider.make_request('evm_snapshot', [])['result']
    yield web3_edf_session
    web3_edf_session.provider.make_request('evm_revert', [snapshot])
