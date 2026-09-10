from cryptography.verify_signature import compute_vs
from transport.msg_providers.onchain_transport import build_deposit_message
from transport.msg_types.deposit import DepositMessage
from utils.bytes import from_hex_string_to_bytes


def get_deposit_message(web3, account_address, pk, module_id) -> DepositMessage:
    latest = web3.eth.get_block('latest')

    prefix = web3.lido.deposit_security_module.get_attest_message_prefix()
    block_number = latest.number
    deposit_root = web3.lido.deposit_contract.get_deposit_root()
    nonce = web3.lido.staking_router.get_staking_module_nonce(module_id)

    # | ATTEST_MESSAGE_PREFIX | blockNumber | blockHash | depositRoot | stakingModuleId | nonce |

    msg_hash = web3.solidity_keccak(
        ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
        [prefix, block_number, latest.hash, deposit_root, module_id, nonce],
    )
    signed = web3.eth.account._sign_hash(msg_hash, private_key=pk)

    return build_deposit_message(
        block_number=latest.number,
        block_hash=latest.hash,
        guardian=account_address,
        deposit_root=deposit_root,
        staking_module_id=module_id,
        nonce=nonce,
        r=signed.r.to_bytes(32, 'big'),
        vs=from_hex_string_to_bytes(compute_vs(signed.v, '0x' + signed.s.to_bytes(32, 'big').hex())),
        version=b'1',
    )


def get_delegated_deposit_message(web3, guardian: str, delegate_pk: str, module_id: int) -> DepositMessage:
    """Build a DSMv5 deposit message: the digest binds the guardian contract, the delegate signs it.

    | ATTEST_MESSAGE_PREFIX | guardian | blockNumber | blockHash | depositRoot | stakingModuleId | nonce |

    Differs from `get_deposit_message` in exactly the two ways v5 does: the guardian address is folded
    into the digest right after the prefix, and the signer is the guardian's delegate rather than the
    guardian itself — so `guardianDelegate` is what the recovered signer must match.
    """
    latest = web3.eth.get_block('latest')
    prefix = web3.lido.deposit_security_module.get_attest_message_prefix()
    deposit_root = web3.lido.deposit_contract.get_deposit_root()
    nonce = web3.lido.staking_router.get_staking_module_nonce(module_id)
    guardian = web3.to_checksum_address(guardian)

    msg_hash = web3.solidity_keccak(
        ['bytes32', 'address', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
        [prefix, guardian, latest.number, latest.hash, deposit_root, module_id, nonce],
    )
    signed = web3.eth.account._sign_hash(msg_hash, private_key=delegate_pk)

    message = build_deposit_message(
        block_number=latest.number,
        block_hash=latest.hash,
        guardian=guardian,
        deposit_root=deposit_root,
        staking_module_id=module_id,
        nonce=nonce,
        r=signed.r.to_bytes(32, 'big'),
        vs=from_hex_string_to_bytes(compute_vs(signed.v, '0x' + signed.s.to_bytes(32, 'big').hex())),
        version=b'2',
    )
    message['guardianDelegate'] = web3.to_checksum_address(web3.eth.account.from_key(delegate_pk).address)
    return message
