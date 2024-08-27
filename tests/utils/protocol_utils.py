from cryptography.verify_signature import compute_vs


def get_deposit_message(web3, account_address, pk, module_id):
    latest = web3.eth.get_block('latest')

    prefix = web3.lido.deposit_security_module.get_attest_message_prefix()
    block_number = latest.number
    deposit_root = '0x' + web3.lido.deposit_contract.get_deposit_root().hex()
    nonce = web3.lido.staking_router.get_staking_module_nonce(module_id)

    # | ATTEST_MESSAGE_PREFIX | blockNumber | blockHash | depositRoot | stakingModuleId | nonce |

    msg_hash = web3.solidity_keccak(
        ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
        [prefix, block_number, latest.hash.hex(), deposit_root, module_id, nonce],
    )
    signed = web3.eth.account._sign_hash(msg_hash, private_key=pk)

    return {
        'type': 'deposit',
        'depositRoot': deposit_root,
        'nonce': nonce,
        'blockNumber': latest.number,
        'blockHash': latest.hash.hex(),
        'guardianAddress': account_address,
        'guardianIndex': 8,
        'stakingModuleId': module_id,
        'signature': {
            'r': '0x' + signed.r.to_bytes(32, 'big').hex(),
            's': '0x' + signed.s.to_bytes(32, 'big').hex(),
            'v': signed.v,
            '_vs': compute_vs(signed.v, '0x' + signed.s.to_bytes(32, 'big').hex()),
        },
    }
