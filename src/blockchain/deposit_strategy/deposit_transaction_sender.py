from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from blockchain.deposit_strategy.curated_module import CuratedModuleDepositStrategy
from blockchain.deposit_strategy.direct_deposit import DirectDepositStrategy
from blockchain.deposit_strategy.interface import ModuleDepositStrategyInterface
from blockchain.typings import Web3
from cryptography.verify_signature import compute_vs
from eth_typing import Hash32
from transport.msg_types.deposit import DepositMessage
from web3.contract.contract import ContractFunction

logger = logging.getLogger(__name__)


class Sender(ABC):
    @abstractmethod
    def set_next(self, handler: Sender) -> Sender:
        pass

    @abstractmethod
    def prepare_and_send(self, module_id: int, quorum: list[DepositMessage], with_flashbots: bool) -> bool:
        pass


class AbstractSender(Sender):
    """
    Chain senders for deposit transactions.
    """
    _next_sender: Sender = None
    _TIMEOUT_IN_BLOCKS = 6

    def __init__(self, w3: Web3, deposit_strategy: ModuleDepositStrategyInterface):
        self._module_deposit_strategy = deposit_strategy
        self._w3 = w3

    def set_next(self, sender: Sender) -> Sender:
        self._next_sender = sender
        return sender

    @staticmethod
    def _prepare_signs_for_deposit(quorum: list[DepositMessage]) -> tuple[tuple[str, str], ...]:
        sorted_messages = sorted(quorum, key=lambda msg: int(msg['guardianAddress'], 16))

        return tuple((msg['signature']['r'], compute_vs(msg['signature']['v'], msg['signature']['s'])) for msg in sorted_messages)

    def prepare_and_send(self, module_id: int, quorum: list[DepositMessage], with_flashbots: bool) -> bool:
        success = self._module_deposit_strategy.is_deposited_keys_amount_ok(module_id) and self._prepare_and_send(quorum, with_flashbots)
        if not success and self._next_sender:
            return self._next_sender.prepare_and_send(module_id, quorum, with_flashbots)

        return False

    @abstractmethod
    def _prepare(self, quorum: list[DepositMessage], with_flashbots: bool) -> ContractFunction:
        pass

    def _send_transaction(
        self,
        tx: ContractFunction,
        flashbots_works: bool
    ) -> bool:
        if tx is None or not self._w3.transaction.check(tx):
            return False
        return self._w3.transaction.send(tx, flashbots_works, self._TIMEOUT_IN_BLOCKS)

    def _prepare_and_send(self, quorum: list[DepositMessage], with_flashbots: bool) -> bool:
        tx = self._prepare(quorum, with_flashbots)
        return self._send_transaction(tx, with_flashbots)


class DirectDepositSender(AbstractSender):

    def __init__(self, w3: Web3):
        deposit_strategy = DirectDepositStrategy(w3)
        super().__init__(w3, deposit_strategy)

    def _prepare(self, quorum: list[DepositMessage], with_flashbots: bool) -> ContractFunction:
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

    def _prepare_and_send(
        self,
        quorum: list[DepositMessage],
        with_flashbots: bool
    ) -> bool:
        """
        Direct deposit overwrites the sending of transaction by swallowing exceptions on transaction sending.
        """
        try:
            return super()._prepare_and_send(quorum, with_flashbots)
        except Exception as e:
            logger.warning({'msg': 'Error while sending the mellow transaction', 'error': str(e)})
            return False


class DepositSender(AbstractSender):
    """
    Deposit via DSM deposit_buffered_ether
    """

    def __init__(self, w3: Web3):
        deposit_strategy = CuratedModuleDepositStrategy(w3)
        super().__init__(w3, deposit_strategy)

    def _prepare(self, quorum: list[DepositMessage], with_flashbots: bool) -> ContractFunction:
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
