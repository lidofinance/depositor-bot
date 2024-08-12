from __future__ import annotations

import logging

from blockchain.typings import Web3
from cryptography.verify_signature import compute_vs
from eth_typing import Hash32
from transport.msg_types.deposit import DepositMessage
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
    def _prepare_signs_for_deposit(quorum: list[DepositMessage]) -> tuple[tuple[str, str], ...]:
        sorted_messages = sorted(quorum, key=lambda msg: int(msg['guardianAddress'], 16))

        return tuple((msg['signature']['r'], compute_vs(msg['signature']['v'], msg['signature']['s'])) for msg in sorted_messages)

    def prepare_and_send(
        self,
        quorum: list[DepositMessage],
        with_flashbots: bool,
        is_mellow: bool,
    ) -> bool:
        tx = self._prepare_mellow_tx(quorum) if is_mellow else self._prepare_general_tx(quorum)
        return self._send_transaction(tx, with_flashbots)

    def _prepare_mellow_tx(self, quorum: list[DepositMessage]) -> ContractFunction:
        block_number = quorum[0]['blockNumber']
        block_hash = Hash32(bytes.fromhex(quorum[0]['blockHash'][2:]))
        deposit_root = Hash32(bytes.fromhex(quorum[0]['depositRoot'][2:]))
        staking_module_nonce = quorum[0]['nonce']
        payload = b''
        guardian_signs = self._prepare_signs_for_deposit(quorum)
        return self._w3.lido.simple_dvt_staking_strategy.convert_and_deposit(
            block_number,
            block_hash,
            deposit_root,
            staking_module_nonce,
            payload,
            guardian_signs,
        )

    def _prepare_general_tx(self, quorum: list[DepositMessage]):
        block_number = quorum[0]['blockNumber']
        block_hash = Hash32(bytes.fromhex(quorum[0]['blockHash'][2:]))
        deposit_root = Hash32(bytes.fromhex(quorum[0]['depositRoot'][2:]))
        staking_module_id = quorum[0]['stakingModuleId']
        staking_module_nonce = quorum[0]['nonce']
        payload = b''
        guardian_signs = self._prepare_signs_for_deposit(quorum)
        return self._w3.lido.deposit_security_module.deposit_buffered_ether(
            block_number,
            block_hash,
            deposit_root,
            staking_module_id,
            staking_module_nonce,
            payload,
            guardian_signs,
        )

    def _send_transaction(
        self,
        tx: ContractFunction,
        flashbots_works: bool
    ) -> bool:
        return self._w3.transaction.check(tx) and self._w3.transaction.send(tx, flashbots_works, self._TIMEOUT_IN_BLOCKS)
