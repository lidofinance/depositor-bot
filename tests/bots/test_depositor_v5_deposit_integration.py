"""End-to-end DSM v5 deposit: delegate-signed quorum submitted on-chain.

This is the test that verifies the parts of the v5 work which are otherwise only checked against a
reading of the Solidity — the guardian-bound attest digest and the `r‖s‖v` GuardianSignature shape.
Council messages are signed by the guardians' real delegate keys, fed to the bot, and the resulting
`depositBufferedEther` has to be accepted by the deployed DSM v5. A wrong digest layout or a wrong
signature encoding cannot pass: the contract recovers through ERC-1271 against `getDelegate()`.

Covered end to end: the delegated sign filter (`msg_types/common.py`), delegate liveness via
`get_guardian_delegates`, quorum grouping, `Sender._prepare_signs_for_deposit` and the submission.
"""

from unittest import mock
from unittest.mock import MagicMock

import pytest

import variables
from blockchain.deposit_strategy.base_deposit_strategy import CSMDepositStrategy, DefaultDepositStrategy
from blockchain.deposit_strategy.deposit_transaction_sender import Sender
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from bots.depositor import DepositorBot
from tests.fixtures.edf import ANVIL_KEYS
from tests.utils.protocol_utils import get_delegated_deposit_message

SUBMIT_ROUNDS = 15


def _impersonate(w3, address: str) -> str:
    address = w3.to_checksum_address(address)
    w3.provider.make_request('anvil_impersonateAccount', [address])
    w3.provider.make_request('anvil_setBalance', [address, '0x500000000000000000000000'])
    return address


def _fill_buffer(w3) -> None:
    """Stake enough ETH that the module can actually be deposited to.

    submit() reverts with STAKE_LIMIT above the current rate-limit bucket, so each round submits only
    what the bucket allows and then mines to let it replenish.
    """
    account = w3.eth.accounts[0]
    w3.provider.make_request('anvil_setBalance', [account, '0x500000000000000000000000'])
    for _ in range(SUBMIT_ROUNDS):
        stake_limit = w3.lido.lido.functions.getCurrentStakeLimit().call()
        value = min(10000 * 10**18, stake_limit)
        if value > 0:
            w3.lido.lido.functions.submit(account).transact({'from': account, 'value': value})
        w3.provider.make_request('anvil_mine', [1])


def _raise_share_limit(w3, module_id: int) -> None:
    """A module with stakeShareLimit 0 gets a zero allocation, so nothing would be deposited."""
    router = w3.lido.staking_router
    role = router.functions.STAKING_MODULE_MANAGE_ROLE().call()
    admin = _impersonate(w3, router.functions.getRoleMember(role, 0).call())
    module = router.functions.getStakingModule(module_id).call()
    router.functions.updateStakingModule(
        module_id,
        10000,
        module.priorityExitShareThreshold or 10000,
        module.stakingModuleFee,
        module.treasuryFee,
        module.maxDepositsPerBlock,
        module.minDepositBlockDistance,
    ).transact({'from': admin})


def _pass_min_deposit_distance(w3, module_id: int) -> None:
    """The upgrade deploys a fresh DSM, so lastDepositBlock starts at the deploy block."""
    distance = w3.lido.staking_router.functions.getStakingModuleMinDepositBlockDistance(module_id).call()
    w3.provider.make_request('anvil_mine', [hex(distance + 1)])
    assert w3.lido.deposit_security_module.is_min_deposit_distance_passed(module_id), 'min deposit distance still not passed'


def _module_with_depositable_keys(w3) -> int:
    for module_id in w3.lido.staking_router.get_staking_module_ids():
        summary = w3.lido.staking_router.functions.getStakingModuleSummary(module_id).call()
        if summary[2] > 0:  # depositableValidatorsCount
            return module_id
    pytest.skip('No staking module on this snapshot has depositable keys.')


def _quorum_messages(w3, guardians: list[str], delegates: dict, module_id: int, count: int) -> list:
    """One delegate-signed message per guardian, all at the same block so they form one quorum."""
    messages = []
    for guardian in guardians:
        delegate = w3.to_checksum_address(delegates[guardian])
        key = ANVIL_KEYS.get(delegate)
        if key is None:
            continue
        messages.append(get_delegated_deposit_message(w3, guardian, key, module_id))
        if len(messages) == count:
            # The DSM verifies blockhash(blockNumber), which is 0 while that block is still the head —
            # so the signed block has to be in the past before the deposit can be simulated or sent.
            w3.provider.make_request('anvil_mine', [1])
            return messages
    pytest.skip(f'Snapshot has fewer than {count} guardians whose delegate keys are known.')


@pytest.fixture
def deposit_bot(web3_edf, set_integration_account):
    """A bot with the real Sender and real strategies — the submission path must not be mocked."""
    # The per-module heartbeat map is built from the whitelist in __init__, so it has to cover every
    # module before construction; a test narrowing the whitelist afterwards is then still safe.
    variables.DEPOSIT_MODULES_WHITELIST = list(web3_edf.lido.staking_router.get_staking_module_ids())
    variables.ENABLE_TOP_UP = False
    web3_edf.lido._load_staking_modules()
    gas_price_calculator = GasPriceCalculator(web3_edf)
    with mock.patch.object(DepositorBot, '_build_consolidation_indexer', return_value=MagicMock()):
        bot = DepositorBot(
            web3_edf,
            Sender(web3_edf),
            DefaultDepositStrategy(web3_edf, gas_price_calculator),
            CSMDepositStrategy(web3_edf, gas_price_calculator),
            gas_price_calculator,
            MagicMock(),
            MagicMock(),
        )
    bot.message_storage.messages = []
    yield bot
    bot.message_storage.messages = []


@pytest.mark.integration
def test_delegate_signed_quorum_lands_a_deposit(deposit_bot, web3_edf, edf_manifest):
    w3 = web3_edf
    assert w3.lido.guardian_delegation_active(), 'snapshot is not on the delegation model'

    module_id = _module_with_depositable_keys(w3)
    _fill_buffer(w3)
    _raise_share_limit(w3, module_id)
    _pass_min_deposit_distance(w3, module_id)

    quorum_size = w3.lido.deposit_security_module.get_guardian_quorum()
    messages = _quorum_messages(w3, edf_manifest['guardians'], edf_manifest['guardianDelegates'], module_id, quorum_size)
    nonce_before = w3.lido.staking_router.get_staking_module_nonce(module_id)

    # Without messages there is no quorum, so nothing must be submitted — this also proves the deposit
    # below was caused by the signatures rather than by anything else the fixture set up.
    deposit_bot.execute(w3.eth.get_block('latest'))
    assert w3.lido.staking_router.get_staking_module_nonce(module_id) == nonce_before

    deposit_bot.message_storage.messages = messages
    assert deposit_bot.execute(w3.eth.get_block('latest'))

    # The module nonce only advances when depositBufferedEther is actually executed by the DSM, so this
    # is proof the guardian-bound digest and the r‖s‖v signature shape were accepted by DSM v5 itself.
    assert w3.lido.staking_router.get_staking_module_nonce(module_id) == nonce_before + 1


@pytest.mark.integration
def test_quorum_is_rejected_when_a_delegate_is_revoked(deposit_bot, web3_edf, edf_manifest):
    """Off-chain liveness check: revoking a delegate must drop that guardian's message, taking the
    quorum below threshold — the bot must not submit a deposit the DSM would reject."""
    w3 = web3_edf
    module_id = _module_with_depositable_keys(w3)
    _fill_buffer(w3)
    _raise_share_limit(w3, module_id)
    _pass_min_deposit_distance(w3, module_id)

    quorum_size = w3.lido.deposit_security_module.get_guardian_quorum()
    messages = _quorum_messages(w3, edf_manifest['guardians'], edf_manifest['guardianDelegates'], module_id, quorum_size)
    nonce_before = w3.lido.staking_router.get_staking_module_nonce(module_id)

    revoked = w3.to_checksum_address(messages[0]['guardianAddress'])
    owner = _impersonate(w3, w3.eth.contract(address=revoked, abi=_OWNER_ABI).functions.owner().call())
    w3.eth.contract(address=revoked, abi=_OWNER_ABI).functions.revokeDelegate().transact({'from': owner})

    deposit_bot.message_storage.messages = messages
    deposit_bot.execute(w3.eth.get_block('latest'))

    assert w3.lido.staking_router.get_staking_module_nonce(module_id) == nonce_before


_OWNER_ABI = [
    {'type': 'function', 'name': 'owner', 'stateMutability': 'view', 'inputs': [], 'outputs': [{'name': '', 'type': 'address'}]},
    {'type': 'function', 'name': 'revokeDelegate', 'stateMutability': 'nonpayable', 'inputs': [], 'outputs': []},
]
