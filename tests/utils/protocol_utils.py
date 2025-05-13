from cryptography.verify_signature import compute_vs
from transport.msg_providers.onchain_transport import DepositParser
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

    return DepositParser.build_message(
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
