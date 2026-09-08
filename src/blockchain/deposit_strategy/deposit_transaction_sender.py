from __future__ import annotations

import logging
from typing import cast

from eth_typing import Hash32
from web3.contract.contract import ContractFunction

from blockchain.contracts.deposit_security_module import GuardianSignature
from blockchain.typings import Web3
from cryptography.verify_signature import to_guardian_signature
from transport.msg_types.deposit import DepositMessage
from utils.bytes import from_hex_string_to_bytes

logger = logging.getLogger(__name__)


class Sender:
    """
    Chain senders for deposit transactions.
    """

    _TIMEOUT_IN_BLOCKS = 6

    def __init__(self, w3: Web3):
        self._w3 = w3

    @staticmethod
    def _prepare_signs_for_deposit(quorum: list[DepositMessage], delegated: bool) -> tuple[GuardianSignature, ...]:
        # The DSM requires signatures strictly ascending by guardian address; guardianAddress is the
        # guardian EOA on DSMv4 and the guardian contract on DSMv5 — the sort key is the same either way.
        sorted_messages = sorted(quorum, key=lambda msg: int(msg['guardianAddress'], 16))

        return tuple(
            to_guardian_signature(msg['guardianAddress'], cast(str, msg['signature']['r']), msg['signature']['_vs'], delegated)
            for msg in sorted_messages
        )

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
        guardian_signs = self._prepare_signs_for_deposit(quorum, self._w3.lido.guardian_delegation_active())

        return self._w3.lido.deposit_security_module.deposit_buffered_ether(
            block_number,
            block_hash,
            deposit_root,
            staking_module_id,
            staking_module_nonce,
            guardian_signs,
        )

    def _send_transaction(self, tx: ContractFunction, flashbots_works: bool) -> bool:
        return self._w3.transaction.check(tx) and self._w3.transaction.send(tx, flashbots_works, self._TIMEOUT_IN_BLOCKS)
