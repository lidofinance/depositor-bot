import logging
from typing import TYPE_CHECKING

from blockchain.contracts.base_interface import ContractInterface
from web3.contract.contract import ContractFunction
from web3.types import BlockIdentifier

if TYPE_CHECKING:
    from blockchain.topup.proofs import TopUpProofData

logger = logging.getLogger(__name__)


class TopUpGatewayContract(ContractInterface):
    abi_path = './interfaces/TopUpGateway.json'

    def can_top_up(self, staking_module_id: int, block_identifier: BlockIdentifier = 'latest') -> bool:
        response = self.functions.canTopUp(staking_module_id).call(block_identifier=block_identifier)
        logger.info({
            'msg': f'Call `canTopUp({staking_module_id})`.',
            'value': response,
            'block_identifier': repr(block_identifier),
        })
        return response

    def top_up(self, module_id: int, proof_data: 'TopUpProofData') -> ContractFunction:
        top_up_data = (
            module_id,
            proof_data.key_indices,
            proof_data.operator_ids,
            proof_data.validator_indices,
            (proof_data.child_block_timestamp, proof_data.slot, proof_data.proposer_index),
            [
                (
                    w.proofs, w.pubkey, w.effective_balance, w.activation_eligibility_epoch,
                    w.activation_epoch, w.exit_epoch, w.withdrawable_epoch, w.slashed,
                )
                for w in proof_data.witnesses
            ],
            proof_data.pending_balances_gwei,
        )
        logger.info({'msg': f'Build `topUp()` tx.', 'module_id': module_id, 'validators': len(proof_data.witnesses)})
        return self.functions.topUp(top_up_data)