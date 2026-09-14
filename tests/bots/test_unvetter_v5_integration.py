"""End-to-end DSM v5 unvet relay against Hoodi's EDF deployment.

Like pause, unvet needs a single guardian signature, so these tests are about that signature reaching
`unvetSigningKeys` and being accepted by DSM v5 — plus the two things the relay owes the council
around it: never paying gas for an intent it cannot authenticate, and not consuming one it failed to
deliver.
"""

from unittest import mock

import pytest

import variables
from blockchain.web3_extentions.transaction import TransactionUtils
from bots.unvetter import UnvetterBot
from tests.fixtures.edf import ANVIL_KEYS
from tests.utils.protocol_utils import get_delegated_unvet_message

# StakingRouter takes both as packed arrays: operator ids as uint64, vetted counts as uint128.
OPERATOR_ID_BYTES = 8
VETTED_COUNT_BYTES = 16


def _signed_unvet(w3, guardian: str, key: str, module_id: int, operator_ids: bytes, vetted_keys: bytes):
    """Sign over a block the DSM can still hash.

    Both mines matter: anvil resolves BLOCKHASH only for blocks it mined itself, not for the forked
    head, and the hash of the head block is zero until another block is on top of it.
    """
    w3.provider.make_request('anvil_mine', [1])
    message = get_delegated_unvet_message(w3, guardian, key, module_id, operator_ids, vetted_keys)
    w3.provider.make_request('anvil_mine', [1])
    return message


def _guardian_with_key(w3) -> tuple[str, str]:
    guardian, delegate = next(iter(w3.edf_guardian_delegates.items()))
    return guardian, ANVIL_KEYS[delegate]


def _other_delegate_key(w3, guardian: str) -> str:
    own = w3.edf_guardian_delegates[guardian]
    return next(key for delegate, key in ANVIL_KEYS.items() if delegate != own)


def _operator_to_unvet(w3) -> tuple[int, bytes, bytes]:
    """An active operator with keys that are vetted but not yet deposited, unvetted down to deposited.

    Anything else is not a decrease and the module would treat the call as a no-op.
    """
    for module_id in w3.lido.staking_router.get_staking_module_ids():
        for digest in w3.lido.staking_router.functions.getNodeOperatorDigests(module_id, 0, 200).call():
            operator_id, is_active, summary = digest[0], digest[1], digest[2]
            deposited, depositable = summary[6], summary[7]
            if is_active and depositable > 0:
                return (
                    module_id,
                    operator_id.to_bytes(OPERATOR_ID_BYTES, 'big'),
                    deposited.to_bytes(VETTED_COUNT_BYTES, 'big'),
                )
    pytest.skip('No active node operator on this chain has vetted-but-undeposited keys.')


@pytest.fixture
def unvet_bot(web3_edf, set_integration_account):
    """A bot with the real sender — the submission path must not be mocked."""
    variables.MESSAGE_TRANSPORTS = ''
    bot = UnvetterBot(web3_edf)
    bot.prepare_transport_bus()
    bot.message_storage.messages = []
    yield bot
    bot.message_storage.messages = []


@pytest.mark.integration
def test_delegate_signed_unvet_lands(unvet_bot, web3_edf):
    w3 = web3_edf
    assert w3.lido.guardian_delegation_active(), 'chain is not on the delegation model'

    guardian, key = _guardian_with_key(w3)
    module_id, operator_ids, vetted_keys = _operator_to_unvet(w3)
    nonce_before = w3.lido.staking_router.get_staking_module_nonce(module_id)
    unvet_bot.message_storage.messages = [_signed_unvet(w3, guardian, key, module_id, operator_ids, vetted_keys)]

    unvet_bot.execute(w3.eth.get_block('latest'))

    # The module nonce only advances when unvetSigningKeys is actually executed by the DSM, so this is
    # proof the guardian-bound digest and the r‖s‖v signature shape were accepted on chain.
    assert w3.lido.staking_router.get_staking_module_nonce(module_id) == nonce_before + 1


@pytest.mark.integration
def test_unvet_attributed_to_a_delegate_who_did_not_sign_it_is_dropped(unvet_bot, web3_edf):
    w3 = web3_edf
    guardian, _ = _guardian_with_key(w3)
    module_id, operator_ids, vetted_keys = _operator_to_unvet(w3)
    nonce_before = w3.lido.staking_router.get_staking_module_nonce(module_id)

    message = _signed_unvet(w3, guardian, _other_delegate_key(w3, guardian), module_id, operator_ids, vetted_keys)
    # Claim the guardian's real delegate signed it. The recovered signer is someone else, so the
    # off-chain filter must drop it instead of paying gas for a call DSM v5 would reject.
    message['guardianDelegate'] = w3.edf_guardian_delegates[guardian]
    unvet_bot.message_storage.messages = [message]

    unvet_bot.execute(w3.eth.get_block('latest'))

    assert w3.lido.staking_router.get_staking_module_nonce(module_id) == nonce_before, 'a forged unvet was relayed'
    assert not unvet_bot.message_storage.messages, 'a message that fails signature checks must not be retained'


@pytest.mark.integration
def test_unvet_is_retried_after_a_failed_delivery(unvet_bot, web3_edf):
    w3 = web3_edf
    guardian, key = _guardian_with_key(w3)
    module_id, operator_ids, vetted_keys = _operator_to_unvet(w3)
    nonce_before = w3.lido.staking_router.get_staking_module_nonce(module_id)
    unvet_bot.message_storage.messages = [_signed_unvet(w3, guardian, key, module_id, operator_ids, vetted_keys)]

    with mock.patch.object(TransactionUtils, 'send', return_value=False):
        unvet_bot.execute(w3.eth.get_block('latest'))

    assert w3.lido.staking_router.get_staking_module_nonce(module_id) == nonce_before
    assert unvet_bot.message_storage.messages, 'an undelivered intent must stay for the next cycle'

    unvet_bot.execute(w3.eth.get_block('latest'))

    assert w3.lido.staking_router.get_staking_module_nonce(module_id) == nonce_before + 1, 'the retained intent was not retried'
