import pytest
from eth_account import Account
from web3 import Web3

from cryptography.verify_signature import compute_vs
from tests.conftest import COUNCIL_ADDRESS_1, COUNCIL_ADDRESS_2, COUNCIL_PK_1
from transport.msg_types.common import get_messages_sign_filter

# Arbitrary but fixed DSMv5 message prefixes and a guardian *contract* address. Under delegation the
# council daemon's delegate EOA signs a digest that folds the guardian address in after the prefix.
_ATTEST_PREFIX = b'\x11' * 32
_PAUSE_PREFIX = b'\x22' * 32
_GUARDIAN = Web3.to_checksum_address('0xabababababababababababababababababababab')
_DELEGATE = COUNCIL_ADDRESS_1  # signs with COUNCIL_PK_1
_BLOCK_HASH = '0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532'
_DEPOSIT_ROOT = '0x64dcf70a7ad7fc6b1a55db6b08b86e9d80736259916fcaef98f4710f0bac687b'


def _sign(pk: str, abi: list[str], data: list) -> dict:
    digest = Web3.solidity_keccak(abi, data)
    signed = Account.unsafe_sign_hash(digest, pk)
    return {
        'r': '0x' + signed.r.to_bytes(32, 'big').hex(),
        '_vs': compute_vs(signed.v, '0x' + signed.s.to_bytes(32, 'big').hex()),
    }


def _deposit_message(guardian: str = _GUARDIAN, delegate: str = _DELEGATE, signer_pk: str = COUNCIL_PK_1) -> dict:
    # The signature is always produced over the digest bound to `guardian`; `delegate` is what the
    # filter compares the recovered signer against.
    signature = _sign(
        signer_pk,
        ['bytes32', 'address', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
        [_ATTEST_PREFIX, guardian, 10, _BLOCK_HASH, _DEPOSIT_ROOT, 1, 12],
    )
    return {
        'type': 'deposit',
        'blockNumber': 10,
        'blockHash': _BLOCK_HASH,
        'depositRoot': _DEPOSIT_ROOT,
        'stakingModuleId': 1,
        'nonce': 12,
        'guardianAddress': guardian,
        'guardianDelegate': delegate,
        'signature': signature,
    }


@pytest.mark.unit
def test_delegated_deposit_signature_accepted():
    sign_filter = get_messages_sign_filter(_ATTEST_PREFIX, delegated=True)
    assert sign_filter(_deposit_message())


@pytest.mark.unit
def test_delegated_rejects_when_delegate_mismatch():
    # Signature is by COUNCIL_ADDRESS_1, but the message claims a different delegate.
    sign_filter = get_messages_sign_filter(_ATTEST_PREFIX, delegated=True)
    assert not sign_filter(_deposit_message(delegate=COUNCIL_ADDRESS_2))


@pytest.mark.unit
def test_delegated_rejects_when_guardian_tampered():
    # Digest binds the guardian; changing guardianAddress after signing invalidates the signature.
    message = _deposit_message()
    message['guardianAddress'] = Web3.to_checksum_address('0xcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd')
    sign_filter = get_messages_sign_filter(_ATTEST_PREFIX, delegated=True)
    assert not sign_filter(message)


@pytest.mark.unit
def test_non_delegated_rejects_delegation_signature():
    # A v5 (guardian-bound) signature must not validate under the v4 scheme (no guardian in digest).
    sign_filter = get_messages_sign_filter(_ATTEST_PREFIX, delegated=False)
    assert not sign_filter(_deposit_message())


@pytest.mark.unit
def test_delegated_pause_signature_accepted():
    signature = _sign(COUNCIL_PK_1, ['bytes32', 'address', 'uint256'], [_PAUSE_PREFIX, _GUARDIAN, 10])
    message = {
        'type': 'pause',
        'blockNumber': 10,
        'guardianAddress': _GUARDIAN,
        'guardianDelegate': _DELEGATE,
        'signature': signature,
    }
    sign_filter = get_messages_sign_filter(_PAUSE_PREFIX, delegated=True)
    assert sign_filter(message)
