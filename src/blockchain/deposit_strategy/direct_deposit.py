import logging
from abc import ABC

from web3.contract.contract import ContractFunction

from blockchain.deposit_strategy.curated_module import CuratedModuleDepositStrategy
from blockchain.deposit_strategy.interface import ModuleDepositStrategyInterface
from blockchain.typings import Web3
from eth_typing import Hash32
from metrics.metrics import DEPOSITABLE_ETHER, POSSIBLE_DEPOSITS_AMOUNT
from transport.msg_types.deposit import DepositMessage

logger = logging.getLogger(__name__)


class DirectDepositStrategy(ModuleDepositStrategyInterface, ABC):
    """
    This strategy falls back to CuratedModuleDepositStrategy if any of checks/transactions were unsuccessful
    """

    def __init__(self, w3: Web3, module_id: int):
        super().__init__(w3, module_id)
        self.fallback = CuratedModuleDepositStrategy(self.w3, module_id)

    def get_possible_deposits_amount(self) -> int:
        depositable_ether = self.w3.lido.lido.get_depositable_ether()
        vault = self.w3.lido.simple_dvt_staking_strategy.vault_balance()
        logger.info({'msg': 'Adding mellow vault balance to the depositable check', 'vault': vault})
        depositable_ether += vault
        DEPOSITABLE_ETHER.labels(self.module_id).set(depositable_ether)

        possible_deposits_amount = self.w3.lido.staking_router.get_staking_module_max_deposits_count(
            self.module_id,
            depositable_ether,
        )
        POSSIBLE_DEPOSITS_AMOUNT.labels(self.module_id).set(possible_deposits_amount)
        return possible_deposits_amount

    def prepare_and_send(self, quorum: list[DepositMessage], with_flashbots: bool) -> bool:
        gas_is_ok = self.fallback.is_gas_price_ok()
        logger.info({'msg': 'Calculate gas recommendations.', 'value': gas_is_ok})

        keys_amount_is_profitable = self.is_deposited_keys_amount_ok()
        logger.info({'msg': 'Calculations deposit recommendations.', 'value': keys_amount_is_profitable})
        if not gas_is_ok or not keys_amount_is_profitable:
            logger.info({'msg': 'Direct deposit failed deposit amount or gas price check'})
            return self.fallback.prepare_and_send(quorum, with_flashbots)

        block_number = quorum[0]['blockNumber']
        block_hash = Hash32(bytes.fromhex(quorum[0]['blockHash'][2:]))
        deposit_root = Hash32(bytes.fromhex(quorum[0]['depositRoot'][2:]))
        staking_module_nonce = quorum[0]['nonce']
        payload = b''
        guardian_signs = self._prepare_signs_for_deposit(quorum)

        success = False
        try:
            mellow_tx = self.w3.lido.simple_dvt_staking_strategy.convert_and_deposit(
                block_number,
                block_hash,
                deposit_root,
                staking_module_nonce,
                payload,
                guardian_signs,
            )
            success = self._send_transaction(mellow_tx, with_flashbots)
            logger.info({'msg': 'Send mellow deposit transaction.', 'with_flashbots': with_flashbots, 'success': success})
        except Exception as e:
            logger.warning({'msg': 'Error while sending the mellow transaction', 'error': str(e)})
        return success or self.fallback.prepare_and_send(quorum, with_flashbots)

    def is_deposited_keys_amount_ok(self) -> bool:
        possible_deposits_amount = self.get_possible_deposits_amount()

        if possible_deposits_amount == 0:
            logger.info(
                {
                    'msg': f'Possible deposits amount is {possible_deposits_amount}. Skip deposit.',
                    'module_id': self.module_id,
                }
            )
            return False

        recommended_max_gas = self.fallback.calculate_recommended_gas_based_on_deposit_amount(possible_deposits_amount)

        base_fee_per_gas = self.fallback.get_pending_base_fee()
        return recommended_max_gas >= base_fee_per_gas
