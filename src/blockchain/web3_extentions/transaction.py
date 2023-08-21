import logging

from eth_account.datastructures import SignedTransaction
from web3.contract import ContractFunction
from web3.exceptions import ContractLogicError, TransactionNotFound, TimeExhausted
from web3.module import Module
from web3.types import BlockData, Wei

import variables
from blockchain.constants import SLOT_TIME
from metrics.metrics import TX_SEND


logger = logging.getLogger(__name__)


class TransactionUtils(Module):
    @staticmethod
    def check(transaction: ContractFunction) -> bool:
        try:
            transaction.call()
        except (ValueError, ContractLogicError) as error:
            logger.error({'msg': 'Local transaction reverted.', 'error': str(error)})
            return False

        logger.info({'msg': 'Tx local call succeed.'})
        return True

    def send(
        self,
        transaction: ContractFunction,
        use_flashbots: bool,
        timeout_in_blocks: int,
    ) -> bool:
        if not variables.ACCOUNT:
            logger.info({'msg': 'Account was not provided. Sending transaction skipped.'})
            return True

        if not variables.CREATE_TRANSACTIONS:
            logger.info({'msg': 'Dry mode activated. Sending transaction skipped.'})
            return True

        pending: BlockData = self.web3.eth.get_block('pending')

        priority = self._get_priority_fee(
            variables.GAS_PRIORITY_FEE_PERCENTILE,
            variables.MIN_PRIORITY_FEE,
            variables.MAX_PRIORITY_FEE,
        )

        transaction = transaction.build_transaction({
            'from': variables.ACCOUNT.address,
            # TODO Estimate gas and min(contract_gas_limit, estimated_gas * 1.3)
            'gas': variables.CONTRACT_GAS_LIMIT,
            'maxFeePerGas': pending['baseFeePerGas'] * 2 + priority,
            'maxPriorityFeePerGas': priority,
            "nonce": self.web3.eth.get_transaction_count(variables.ACCOUNT.address),
        })

        signed = self.web3.eth.account.sign_transaction(transaction, variables.ACCOUNT.privateKey)

        # TODO try to deposit with other relays
        if use_flashbots and getattr(self.web3, 'flashbots', None):
            status = self.flashbots_send(signed, pending['number'], timeout_in_blocks)
        else:
            status = self.classic_send(signed, timeout_in_blocks)

        if status:
            TX_SEND.label('success').inc()
            logger.info({'msg': 'Transaction found in blockchain.'})
        else:
            TX_SEND.label('failure').inc()
            logger.warning({'msg': 'Transaction not found in blockchain.'})

        return status

    def flashbots_send(
        self,
        signed_tx: SignedTransaction,
        pending_block_num: int,
        timeout_in_blocks: int,
    ) -> bool:
        for i in range(timeout_in_blocks):
            result = self.web3.flashbots.send_bundle(
                [{"signed_transaction": signed_tx.rawTransaction}],
                pending_block_num + i
            )

        logger.info({'msg': 'Transaction sent.'})
        try:
            rec = result.receipts()
        except TransactionNotFound:
            return False
        else:
            logger.info({'msg': 'Transaction mined.', 'value': rec[-1]['transactionHash'].hex()})
            return True

    def classic_send(self, signed_tx: SignedTransaction, timeout_in_blocks: int) -> bool:
        try:
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        except Exception as error:
            logger.error({'msg': 'Transaction reverted.', 'value': str(error)})
            return False

        logger.info({'msg': 'Transaction sent.', 'value': tx_hash.hex()})
        try:
            tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, (timeout_in_blocks + 1) * SLOT_TIME)
        except TimeExhausted:
            return False

        logger.info({'msg': 'Transaction found', 'value': tx_receipt['transactionHash'].hex()})
        return True

    def _get_priority_fee(self, percentile: int, min_priority_fee: Wei, max_priority_fee: Wei):
        return min(
            max(
                self.web3.eth.fee_history(1, 'latest', reward_percentiles=[percentile])['reward'][0][0],
                min_priority_fee,
            ),
            max_priority_fee,
        )
