import logging
from functools import lru_cache

from blockchain.contracts.base_interface import ContractInterface
from blockchain.topup.types import TopUpProofData
from web3.contract.contract import ContractFunction
from web3.types import BlockIdentifier

logger = logging.getLogger(__name__)


class TopUpGatewayContract(ContractInterface):
    abi_path = './interfaces/TopUpGateway.json'

    @lru_cache(maxsize=1)
    def get_max_validators_per_top_up(self, block_identifier: BlockIdentifier = 'latest') -> int:
        response = self.functions.getMaxValidatorsPerTopUp().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getMaxValidatorsPerTopUp()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    @lru_cache(maxsize=1)
    def get_target_balance_gwei(self, block_identifier: BlockIdentifier = 'latest') -> int:
        response = self.functions.getTargetBalanceGwei().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getTargetBalanceGwei()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    @lru_cache(maxsize=1)
    def get_min_top_up_gwei(self, block_identifier: BlockIdentifier = 'latest') -> int:
        response = self.functions.getMinTopUpGwei().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getMinTopUpGwei()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def is_paused(self, block_identifier: BlockIdentifier = 'latest') -> bool:
        response = self.functions.isPaused().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `isPaused()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def is_block_distance_passed(self, block_identifier: BlockIdentifier = 'latest') -> bool:
        response = self.functions.isBlockDistancePassed().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `isBlockDistancePassed()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def top_up(self, module_id: int, proof_data: 'TopUpProofData') -> ContractFunction:
        top_up_data = (
            module_id,
            proof_data.key_indices,
            proof_data.operator_ids,
            proof_data.validator_indices,
            (proof_data.child_block_timestamp, proof_data.slot, proof_data.proposer_index),
            [w.tuple() for w in proof_data.witnesses],
            proof_data.pending_balances_gwei,
        )
        logger.info({'msg': 'Build `topUp()` tx.', 'module_id': module_id, 'validators': len(proof_data.witnesses)})
        return self.functions.topUp(top_up_data)
