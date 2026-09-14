"""End-to-end DSM v5 pause relay against Hoodi's EDF deployment.

The pause path is the one place where a single guardian signature is authority enough, so these
tests are about that signature: that a delegate-signed intent reaches `pauseDeposits` and is accepted
by DSM v5, that one attributed to a delegate who did not sign it never leaves the process, and that a
delivery failure leaves the intent to be retried rather than consuming it.
"""

from unittest import mock

import pytest

import variables
from blockchain.web3_extentions.transaction import TransactionUtils
from bots.pauser import PauserBot
from tests.fixtures.edf import ANVIL_KEYS
from tests.utils.protocol_utils import get_delegated_pause_message


def _guardian_with_key(w3) -> tuple[str, str]:
    guardian, delegate = next(iter(w3.edf_guardian_delegates.items()))
    return guardian, ANVIL_KEYS[delegate]


def _other_delegate_key(w3, guardian: str) -> str:
    own = w3.edf_guardian_delegates[guardian]
    return next(key for delegate, key in ANVIL_KEYS.items() if delegate != own)


@pytest.fixture
def pause_bot(web3_edf, set_integration_account):
    """A bot with the real sender — the submission path must not be mocked."""
    variables.MESSAGE_TRANSPORTS = ''
    bot = PauserBot(web3_edf)
    bot.message_storage.messages = []
    yield bot
    bot.message_storage.messages = []


@pytest.mark.integration
def test_delegate_signed_pause_pauses_deposits(pause_bot, web3_edf):
    w3 = web3_edf
    assert w3.lido.guardian_delegation_active(), 'chain is not on the delegation model'
    assert not w3.lido.deposit_security_module.is_deposits_paused(), 'deposits are already paused'

    guardian, key = _guardian_with_key(w3)
    pause_bot.message_storage.messages = [get_delegated_pause_message(w3, guardian, key)]

    pause_bot.execute(w3.eth.get_block('latest'))

    # Only DSM v5 itself can flip this, so it is proof the guardian-bound digest and the r‖s‖v
    # signature shape were accepted on chain.
    assert w3.lido.deposit_security_module.is_deposits_paused(), 'a valid delegate-signed pause did not land'


@pytest.mark.integration
def test_pause_attributed_to_a_delegate_who_did_not_sign_it_is_dropped(pause_bot, web3_edf):
    w3 = web3_edf
    guardian, _ = _guardian_with_key(w3)
    message = get_delegated_pause_message(w3, guardian, _other_delegate_key(w3, guardian))
    # Claim the guardian's real delegate signed it. The recovered signer is someone else, so the
    # off-chain filter must drop it instead of paying gas for a call DSM v5 would reject.
    message['guardianDelegate'] = w3.edf_guardian_delegates[guardian]
    pause_bot.message_storage.messages = [message]

    pause_bot.execute(w3.eth.get_block('latest'))

    assert not w3.lido.deposit_security_module.is_deposits_paused(), 'a forged pause was relayed'
    assert not pause_bot.message_storage.messages, 'a message that fails signature checks must not be retained'


@pytest.mark.integration
def test_pause_is_retried_after_a_failed_delivery(pause_bot, web3_edf):
    w3 = web3_edf
    guardian, key = _guardian_with_key(w3)
    pause_bot.message_storage.messages = [get_delegated_pause_message(w3, guardian, key)]

    with mock.patch.object(TransactionUtils, 'send', return_value=False):
        pause_bot.execute(w3.eth.get_block('latest'))

    assert not w3.lido.deposit_security_module.is_deposits_paused()
    assert pause_bot.message_storage.messages, 'an undelivered intent must stay for the next cycle'

    pause_bot.execute(w3.eth.get_block('latest'))

    assert w3.lido.deposit_security_module.is_deposits_paused(), 'the retained intent was not retried'
