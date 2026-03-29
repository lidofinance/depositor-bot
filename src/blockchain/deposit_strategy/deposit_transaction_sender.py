from __future__ import annotations

import logging

from blockchain.typings import Web3
from cryptography.verify_signature import recover_vs
from eth_account.account import VRS
from eth_typing import Hash32
from transport.msg_types.deposit import DepositMessage
from utils.bytes import from_hex_string_to_bytes
from web3 import Web3 as BaseWeb3
from web3.contract.contract import ContractFunction

logger = logging.getLogger(__name__)


class Sender:
    """
    Chain senders for deposit transactions.
    """

    _TIMEOUT_IN_BLOCKS = 6

    def __init__(self, w3: Web3):
        self._w3 = w3

    @staticmethod
    def _prepare_signs_for_deposit(quorum: list[DepositMessage]) -> tuple[tuple[VRS, str], ...]:
        sorted_messages = sorted(quorum, key=lambda msg: int(msg['guardianAddress'], 16))

        return tuple((msg['signature']['r'], msg['signature']['_vs']) for msg in sorted_messages)

    def prepare_and_send(
        self,
        quorum: list[DepositMessage],
        with_flashbots: bool,
    ) -> bool:
        tx = self._prepare_general_tx(quorum)
        return self._send_transaction(tx, with_flashbots)

    def _prepare_general_tx(self, quorum: list[DepositMessage]):
        block_number = quorum[0]['blockNumber']
        block_hash = Hash32(from_hex_string_to_bytes(quorum[0]['blockHash']))
        deposit_root = Hash32(from_hex_string_to_bytes(quorum[0]['depositRoot']))
        staking_module_id = quorum[0]['stakingModuleId']
        staking_module_nonce = quorum[0]['nonce']
        payload = b''
        guardian_signs = self._prepare_signs_for_deposit(quorum)
        attest_message_prefix = None
        msg_hash = None
        recovered_guardians = []
        try:
            prefix = self._w3.lido.deposit_security_module.get_attest_message_prefix()
            if isinstance(prefix, bytes):
                attest_message_prefix = prefix.hex()
                msg_hash = BaseWeb3.solidity_keccak(
                    ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
                    [prefix, block_number, block_hash, deposit_root, staking_module_id, staking_module_nonce],
                )
                for msg in quorum:
                    try:
                        signature = msg['signature']
                        if '_vs' in signature and signature.get('r'):
                            v, s = recover_vs(signature['_vs'])
                            recovered_guardians.append(
                                BaseWeb3().eth.account._recover_hash(
                                    msg_hash,
                                    vrs=(v, signature['r'], hex(s)),
                                )
                            )
                        else:
                            recovered_guardians.append(None)
                    except Exception:
                        recovered_guardians.append(None)
            else:
                recovered_guardians = [None] * len(quorum)
        except Exception:
            recovered_guardians = [None] * len(quorum)
        logger.info(
            {
                'msg': 'Prepare depositBufferedEther tx.',
                'block_number': block_number,
                'block_hash': block_hash.hex(),
                'deposit_root': deposit_root.hex(),
                'staking_module_id': staking_module_id,
                'staking_module_nonce': staking_module_nonce,
                'quorum_size': len(quorum),
                'attest_message_prefix': attest_message_prefix,
                'attest_message_hash': msg_hash.hex() if msg_hash is not None else None,
                'guardian_addresses': [msg['guardianAddress'] for msg in quorum],
                'recovered_guardians': recovered_guardians,
            }
        )
        return self._w3.lido.deposit_security_module.deposit_buffered_ether(
            block_number,
            block_hash,
            deposit_root,
            staking_module_id,
            staking_module_nonce,
            payload,
            guardian_signs,
        )

    def _send_transaction(self, tx: ContractFunction, flashbots_works: bool) -> bool:
        return self._w3.transaction.check(tx) and self._w3.transaction.send(tx, flashbots_works, self._TIMEOUT_IN_BLOCKS)
