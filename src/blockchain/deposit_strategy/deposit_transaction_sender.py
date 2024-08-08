from __future__ import annotations

import logging
from typing import Optional

import variables
from blockchain.contracts.staking_module import StakingModuleContract
from blockchain.deposit_strategy.base_deposit_strategy import BaseDepositStrategy
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from blockchain.typings import Web3
from cryptography.verify_signature import compute_vs
from eth_typing import Hash32

from metrics.metrics import MELLOW_VAULT_BALANCE
from transport.msg_types.deposit import DepositMessage
from web3.contract.contract import ContractFunction

logger = logging.getLogger(__name__)


class Sender:
    """
    Chain senders for deposit transactions.
    """
    _TIMEOUT_IN_BLOCKS = 6
    _next_sender: Sender = None

    def __init__(self, w3: Web3, gas_price_calculator: GasPriceCalculator, strategy: BaseDepositStrategy):
        self._w3 = w3
        self._gas_price_calculator = gas_price_calculator
        self._strategy = strategy

    def add_sender(self, sender: Sender):
        self._next_sender = sender
        return sender

    @staticmethod
    def _prepare_signs_for_deposit(quorum: list[DepositMessage]) -> tuple[tuple[str, str], ...]:
        sorted_messages = sorted(quorum, key=lambda msg: int(msg['guardianAddress'], 16))

        return tuple((msg['signature']['r'], compute_vs(msg['signature']['v'], msg['signature']['s'])) for msg in sorted_messages)

    def prepare_and_send(
        self,
        module_id: int,
        quorum: list[DepositMessage],
        with_flashbots: bool,
    ) -> bool:
        if not self._sender_checks(module_id):
            return self._next_sender.prepare_and_send(module_id, quorum, with_flashbots)

        tx = self._prepare_tx(quorum)
        if tx is None or not self._send_transaction(tx, with_flashbots):
            return self._next_sender.prepare_and_send(module_id, quorum, with_flashbots)

        return True

    def _prepare_tx(self, quorum: list[DepositMessage]) -> Optional[ContractFunction]:
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

    def _sender_checks(self, module_id: int) -> bool:
        is_deposit_amount_ok = self._gas_price_calculator.calculate_deposit_recommendation(self._strategy, module_id)
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': is_deposit_amount_ok})
        return is_deposit_amount_ok


class MellowSender(Sender):

    def _prepare_tx(self, quorum: list[DepositMessage]) -> Optional[ContractFunction]:
        block_number = quorum[0]['blockNumber']
        block_hash = Hash32(bytes.fromhex(quorum[0]['blockHash'][2:]))
        deposit_root = Hash32(bytes.fromhex(quorum[0]['depositRoot'][2:]))
        staking_module_nonce = quorum[0]['nonce']
        payload = b''
        try:
            guardian_signs = self._prepare_signs_for_deposit(quorum)
            return self._w3.lido.simple_dvt_staking_strategy.convert_and_deposit(
                block_number,
                block_hash,
                deposit_root,
                staking_module_nonce,
                payload,
                guardian_signs,
            )
        except Exception as e:
            logger.info({'msg': 'Mellow tx preparation has been failed', 'error': repr(e)})
            return None

    def _send_transaction(
        self,
        tx: ContractFunction,
        flashbots_works: bool
    ) -> bool:
        try:
            return self._w3.transaction.check(tx) and self._w3.transaction.send(tx, flashbots_works, self._TIMEOUT_IN_BLOCKS)
        except Exception as e:
            logger.info({'msg': 'Mellow tx sending has been failed', 'error': repr(e)})
            return False

    def _sender_checks(self, module_id: int) -> bool:
        if not variables.MELLOW_CONTRACT_ADDRESS:
            return False
        try:
            buffered = self._w3.lido.lido.get_buffered_ether()
            unfinalized = self._w3.lido.lido_locator.withdrawal_queue_contract.unfinalized_st_eth()
            if buffered < unfinalized:
                return False
            staking_module_contract: StakingModuleContract = self._w3.lido.simple_dvt_staking_strategy.staking_module_contract
            if staking_module_contract.get_staking_module_id() != module_id:
                logger.debug(
                    {
                        'msg': 'Mellow module check failed.',
                        'contract_module': staking_module_contract.get_staking_module_id(),
                        'tx_module': module_id
                    }
                )
                return False
            balance = self._w3.lido.simple_dvt_staking_strategy.vault_balance()
        except Exception as e:
            logger.warning(
                {
                    'msg': 'Failed to check if mellow depositable',
                    'module_id': module_id,
                    'err': repr(e)
                }
            )
            return False
        MELLOW_VAULT_BALANCE.labels(module_id).set(balance)
        if balance < variables.VAULT_DIRECT_DEPOSIT_THRESHOLD:
            logger.info({'msg': f'{balance} is less than VAULT_DIRECT_DEPOSIT_THRESHOLD while building mellow transaction.'})
            return False
        logger.debug({'msg': 'Mellow module check succeeded.', 'tx_module': module_id})
        return super()._sender_checks(module_id)
