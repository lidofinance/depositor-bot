"""End-to-end delegated top-up execution against core's EDF chain.

Drives the bot's own code — `LidoContracts._load_delegation`, `DepositorBot._resolve_topup_path`,
`_validate_topup_delegation`, `DelegationContract.wrap` and `TransactionUtils.check` — against
delegation contracts deployed by **core's** `DelegationFactory`, with `TOP_UP_ROLE` really granted on
the real `TopUpGateway` by its real admin.

Runs on the chain produced by core's own EDF upgrade (see `tests/fixtures/edf.py`): DSM v5, guardians
that are delegation contracts. Deliberately not the revision already deployed on the testnet — that
one predates core's source (it exposes `assignDelegate` rather than `nominateDelegate`) and sits on a
chain still running DSM v4, where the delegation paths in the bot are no-ops.
"""

from unittest import mock
from unittest.mock import MagicMock

import pytest
from web3 import Web3
from web3.exceptions import ContractLogicError
from web3.logs import DISCARD

import tests.fixtures.edf
import variables
from blockchain.topup.types import TopUpProofData
from bots.depositor import DepositorBot, TopUpPath

# web3 surfaces an undecoded custom error, so the rejection is identified by selector. Derived rather
# than hardcoded so it cannot silently be the wrong four bytes.
ACCESS_CONTROL_UNAUTHORIZED = Web3.keccak(text='AccessControlUnauthorizedAccount(address,bytes32)')[:4].hex()

FACTORY_ABI = [
    {
        'type': 'function',
        'name': 'deploy',
        'stateMutability': 'nonpayable',
        'inputs': [
            {'name': 'owner', 'type': 'address'},
            {'name': 'delegate', 'type': 'address'},
            {'name': 'cooldown', 'type': 'uint256'},
        ],
        'outputs': [{'name': 'instance', 'type': 'address'}],
    },
    {
        'type': 'event',
        'name': 'DelegationContractDeployed',
        'anonymous': False,
        'inputs': [
            {'name': 'instance', 'type': 'address', 'indexed': True},
            {'name': 'owner', 'type': 'address', 'indexed': True},
            {'name': 'delegate', 'type': 'address', 'indexed': True},
            {'name': 'cooldown', 'type': 'uint256', 'indexed': False},
        ],
    },
]

# Owner-side operations the bot itself must never call, so they are kept out of the production ABI
# (interfaces/DelegationContract.json declares only what the bot may reach).
#
# Both spellings of the rotation entry point are declared. Core's revision has `nominateDelegate`; the
# one already deployed on the testnet (deploy-hoodi.json, git-ref accf2253) still has the older
# `assignDelegate`. `_nominate_delegate` picks whichever the bytecode actually exposes, so refreshing
# the snapshot across that rename fails no test — calling the absent name reverts with empty data,
# which is undecodable and would be a confusing failure.
OWNER_ABI = [
    {
        'type': 'function',
        'name': 'assignDelegate',
        'stateMutability': 'nonpayable',
        'inputs': [{'name': 'delegate', 'type': 'address'}],
        'outputs': [],
    },
    {
        'type': 'function',
        'name': 'nominateDelegate',
        'stateMutability': 'nonpayable',
        'inputs': [{'name': 'delegate', 'type': 'address'}],
        'outputs': [],
    },
    {'type': 'function', 'name': 'revokeDelegate', 'stateMutability': 'nonpayable', 'inputs': [], 'outputs': []},
    {'type': 'function', 'name': 'terminate', 'stateMutability': 'nonpayable', 'inputs': [], 'outputs': []},
    {'type': 'function', 'name': 'getDelegate', 'stateMutability': 'view', 'inputs': [], 'outputs': [{'name': '', 'type': 'address'}]},
]

# Accounts 1..7 are the guardians' delegates on this chain, so the bot uses 0 and these tests own
# 8 and 9. The owner must differ from the delegate (OwnerCannotBeDelegate).
DELEGATION_OWNER = tests.fixtures.edf.DELEGATION_OWNER
OTHER_DELEGATE = tests.fixtures.edf.SPARE_DELEGATE

EMPTY_PROOF = TopUpProofData(
    child_block_timestamp=0,
    slot=0,
    proposer_index=0,
    witnesses=[],
    validator_indices=[],
    key_indices=[],
    operator_ids=[],
    pending_balances_gwei=[],
)


def _fund_and_impersonate(w3, address: str) -> str:
    w3.provider.make_request('anvil_impersonateAccount', [address])
    w3.provider.make_request('anvil_setBalance', [address, '0x500000000000000000000000'])
    return address


def _deploy_delegation(w3, factory_address: str, delegate: str, cooldown: int = 0) -> str:
    """Deploy a delegation contract through the factory core's upgrade deployed."""
    factory = w3.eth.contract(address=w3.to_checksum_address(factory_address), abi=FACTORY_ABI)
    owner = _fund_and_impersonate(w3, DELEGATION_OWNER)
    tx = factory.functions.deploy(owner, w3.to_checksum_address(delegate), cooldown).transact({'from': owner})
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    # DISCARD: the receipt also carries the new contract's own events, which this minimal ABI cannot
    # decode. Without it web3 warns on each one.
    events = factory.events.DelegationContractDeployed().process_receipt(receipt, errors=DISCARD)
    assert events, 'DelegationContractDeployed was not emitted'
    address = w3.to_checksum_address(events[0]['args']['instance'])
    assert w3.eth.get_code(address), 'delegation contract has no bytecode'
    return address


def _grant_top_up_role(w3, holder: str) -> None:
    gateway = w3.lido.topup_gateway
    role = gateway.top_up_role()
    admin_role = gateway.functions.DEFAULT_ADMIN_ROLE().call()
    admin = w3.to_checksum_address(gateway.functions.getRoleMembers(admin_role).call()[0])
    _fund_and_impersonate(w3, admin)
    tx = gateway.functions.grantRole(role, w3.to_checksum_address(holder)).transact({'from': admin})
    w3.eth.wait_for_transaction_receipt(tx)
    assert gateway.has_role(role, w3.to_checksum_address(holder)), 'grantRole did not take effect'


def _owner_contract(w3, address: str):
    return w3.eth.contract(address=w3.to_checksum_address(address), abi=OWNER_ABI)


def _nominate_delegate(w3, address: str, owner: str, new_delegate: str):
    """Start a delegate rotation, using whichever name the deployed revision exposes."""
    code = w3.eth.get_code(w3.to_checksum_address(address)).hex()
    selector = Web3.keccak(text='nominateDelegate(address)')[:4].hex()
    name = 'nominateDelegate' if selector in code else 'assignDelegate'
    contract = _owner_contract(w3, address)
    tx = contract.functions[name](w3.to_checksum_address(new_delegate)).transact({'from': owner})
    return w3.eth.wait_for_transaction_receipt(tx)


def _use_delegation(w3, address: str | None) -> None:
    """Point the bot's configuration at a delegation contract and reload it, as startup would."""
    variables.DELEGATION_CONTRACT_ADDRESS = w3.to_checksum_address(address) if address else None
    w3.lido._load_delegation()


@pytest.fixture
def bot(web3_edf, set_integration_account):
    with mock.patch.object(DepositorBot, '_build_consolidation_indexer', return_value=MagicMock()):
        instance = DepositorBot(
            web3_edf,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
    yield instance
    _use_delegation(web3_edf, None)


@pytest.fixture
def delegated(bot, web3_edf, edf_manifest):
    """A delegation contract holding TOP_UP_ROLE with the bot's account as its delegate."""
    address = _deploy_delegation(web3_edf, edf_manifest['delegationFactory'], variables.ACCOUNT.address)
    _grant_top_up_role(web3_edf, address)
    _use_delegation(web3_edf, address)
    return address


@pytest.mark.integration
def test_resolves_to_delegated_when_role_sits_on_the_delegation_contract(bot, delegated):
    assert bot._resolve_topup_path() is TopUpPath.DELEGATED
    # ENABLE_TOP_UP has to be on or the startup gate early-returns and asserting on it proves nothing.
    with mock.patch.object(variables, 'ENABLE_TOP_UP', True):
        bot._validate_topup_delegation()  # must not raise
    assert bot._topup_path is TopUpPath.DELEGATED


@pytest.mark.integration
def test_wrapping_moves_the_access_control_boundary(bot, delegated, web3_edf):
    """The point of the whole feature: the bot's key cannot call topUp, but the same key can drive it
    through the delegation contract. Proven by *which* revert each form produces — the direct call is
    stopped by AccessControl, the wrapped one gets past it and fails later inside topUp on the
    deliberately empty proof."""
    w3 = web3_edf
    direct = w3.lido.topup_gateway.top_up(1, EMPTY_PROOF)
    wrapped = w3.lido.delegation.wrap(direct)
    sender = {'from': variables.ACCOUNT.address}

    with pytest.raises(ContractLogicError) as direct_error:
        direct.call(sender)
    rejection = str(direct_error.value)
    assert ACCESS_CONTROL_UNAUTHORIZED in rejection
    # ...and it is specifically our key being refused this role, not some unrelated failure.
    assert variables.ACCOUNT.address[2:].lower() in rejection.lower()
    assert w3.lido.topup_gateway.top_up_role().hex() in rejection.lower()

    with pytest.raises(ContractLogicError) as wrapped_error:
        wrapped.call(sender)
    assert ACCESS_CONTROL_UNAUTHORIZED not in str(wrapped_error.value), 'delegated call was still rejected by AccessControl'

    # And the bot's own dry-run agrees: neither form is submittable with an empty proof, but only the
    # direct one fails for a reason the operator can do nothing about.
    assert w3.transaction.check(wrapped) is False


@pytest.mark.integration
def test_falls_back_to_direct_when_delegate_is_revoked(bot, delegated, web3_edf):
    """Revocation must not strand the bot while its own key can still do the job."""
    w3 = web3_edf
    _grant_top_up_role(w3, variables.ACCOUNT.address)
    owner = _fund_and_impersonate(w3, DELEGATION_OWNER)
    tx = _owner_contract(w3, delegated).functions.revokeDelegate().transact({'from': owner})
    w3.eth.wait_for_transaction_receipt(tx)

    assert bot._resolve_topup_path() is TopUpPath.DIRECT


@pytest.mark.integration
def test_reports_not_delegate_when_revoked_and_key_has_no_role(bot, delegated, web3_edf):
    w3 = web3_edf
    owner = _fund_and_impersonate(w3, DELEGATION_OWNER)
    tx = _owner_contract(w3, delegated).functions.revokeDelegate().transact({'from': owner})
    w3.eth.wait_for_transaction_receipt(tx)

    assert bot._resolve_topup_path() is TopUpPath.NOT_DELEGATE
    with mock.patch.object(variables, 'ENABLE_TOP_UP', True), pytest.raises(ValueError, match='No usable path'):
        bot._validate_topup_delegation()


@pytest.mark.integration
def test_reports_terminated_after_termination(bot, delegated, web3_edf):
    w3 = web3_edf
    owner = _fund_and_impersonate(w3, DELEGATION_OWNER)
    tx = _owner_contract(w3, delegated).functions.terminate().transact({'from': owner})
    w3.eth.wait_for_transaction_receipt(tx)

    assert bot._resolve_topup_path() is TopUpPath.TERMINATED


@pytest.mark.integration
def test_current_delegate_stays_effective_during_rotation_cooldown(bot, web3_edf, edf_manifest):
    """Make-before-break, verified against the real contract rather than inferred from core's tests:
    after nominateDelegate the incumbent is still the effective delegate until the cooldown elapses,
    so a key rotation does not create a gap for the bot."""
    w3 = web3_edf
    address = _deploy_delegation(w3, edf_manifest['delegationFactory'], variables.ACCOUNT.address, cooldown=3600)
    _grant_top_up_role(w3, address)
    _use_delegation(w3, address)
    assert bot._resolve_topup_path() is TopUpPath.DELEGATED

    owner = _fund_and_impersonate(w3, DELEGATION_OWNER)
    _nominate_delegate(w3, address, owner, OTHER_DELEGATE)

    assert w3.to_checksum_address(_owner_contract(w3, address).functions.getDelegate().call()) == variables.ACCOUNT.address
    assert bot._resolve_topup_path() is TopUpPath.DELEGATED

    w3.provider.make_request('evm_increaseTime', [3601])
    w3.provider.make_request('evm_mine', [])
    assert bot._resolve_topup_path() is TopUpPath.NOT_DELEGATE


@pytest.mark.integration
def test_reports_no_role_when_neither_identity_holds_it(bot, web3_edf):
    """The pre-existing misconfiguration this surfaced: role never granted to the bot's key."""
    _use_delegation(web3_edf, None)
    assert bot._resolve_topup_path() is TopUpPath.NO_ROLE
