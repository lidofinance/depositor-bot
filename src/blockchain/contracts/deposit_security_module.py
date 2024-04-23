import logging

from eth_typing import ChecksumAddress, Hash32
from web3.contract.contract import ContractFunction
from web3.types import BlockIdentifier

from blockchain.contracts.base_interface import ContractInterface


logger = logging.getLogger(__name__)


class DepositSecurityModuleContract(ContractInterface):
    abi_path = './interfaces/DepositSecurityModule.json'

    def get_guardian_quorum(self, block_identifier: BlockIdentifier = 'latest') -> int:
        """Returns number of valid guardian signatures required to vet (depositRoot, nonce) pair."""
        response = self.functions.getGuardianQuorum().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getGuardianQuorum()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def get_guardians(self, block_identifier: BlockIdentifier = 'latest') -> list[ChecksumAddress]:
        """Returns guardian committee member list."""
        response = self.functions.getGuardians().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getGuardians()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def get_attest_message_prefix(self, block_identifier: BlockIdentifier = 'latest') -> bytes:
        response = self.functions.ATTEST_MESSAGE_PREFIX().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `ATTEST_MESSAGE_PREFIX()`.', 'value': response.hex(), 'block_identifier': repr(block_identifier)})
        return response

    def can_deposit(self, staking_module_id: int, block_identifier: BlockIdentifier = 'latest') -> bool:
        """
        Returns whether LIDO.deposit() can be called, given that the caller will provide
        guardian attestations of non-stale deposit root and `nonce`, and the number of
        such attestations will be enough to reach quorum.
        """
        response = self.functions.canDeposit(staking_module_id).call(block_identifier=block_identifier)
        logger.info({'msg': f'Call `canDeposit({staking_module_id})`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def deposit_buffered_ether(
        self,
        block_number: int,
        block_hash: Hash32,
        deposit_root: Hash32,
        staking_module_id: int,
        nonce: int,
        deposit_call_data: bytes,
        guardian_signatures: list[tuple[str, str]],
    ) -> ContractFunction:
        """
        Calls LIDO.deposit(maxDepositsPerBlock, stakingModuleId, depositCalldata).

        Reverts if any of the following is true:
        1. IDepositContract.get_deposit_root() != depositRoot.
        2. StakingModule.getNonce() != nonce.
        3. The number of guardian signatures is less than getGuardianQuorum().
        4. An invalid or non-guardian signature received.
        5. block.number - StakingModule.getLastDepositBlock() < minDepositBlockDistance.
        6. blockhash(blockNumber) != blockHash.

        Signatures must be sorted in ascending order by address of the guardian. Each signature must
        be produced for the keccak256 hash of the following message (each component taking 32 bytes):

        | ATTEST_MESSAGE_PREFIX | blockNumber | blockHash | depositRoot | stakingModuleId | nonce |
        """
        tx = self.functions.depositBufferedEther(
            block_number,
            block_hash,
            deposit_root,
            staking_module_id,
            nonce,
            deposit_call_data,
            guardian_signatures,
        )
        logger.info({'msg': 'Build `depositBufferedEther({}, {}, {}, {}, {}, {}, {})` tx.'.format(
            block_number,
            block_hash,
            deposit_root,
            staking_module_id,
            nonce,
            deposit_call_data,
            guardian_signatures,
        )})
        return tx

    def get_pause_message_prefix(self, block_identifier: BlockIdentifier = 'latest') -> bytes:
        response = self.functions.PAUSE_MESSAGE_PREFIX().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `PAUSE_MESSAGE_PREFIX()`.', 'value': response.hex(), 'block_identifier': repr(block_identifier)})
        return response

    def get_pause_intent_validity_period_blocks(self, block_identifier: BlockIdentifier = 'latest') -> int:
        """Returns current `pauseIntentValidityPeriodBlocks` contract parameter (see `pauseDeposits`)."""
        response = self.functions.getPauseIntentValidityPeriodBlocks().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getPauseIntentValidityPeriodBlocks()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def pause_deposits(
        self,
        block_number: int,
        staking_module_id: int,
        guardian_signature: tuple[str, str],
    ) -> ContractFunction:
        """
        Pauses deposits for staking module given that both conditions are satisfied (reverts otherwise):

            1. The function is called by the guardian with index guardianIndex OR sig
                is a valid signature by the guardian with index guardianIndex of the data
                defined below.

            2. block.number - blockNumber <= pauseIntentValidityPeriodBlocks

        The signature, if present, must be produced for keccak256 hash of the following
        message (each component taking 32 bytes):

        | PAUSE_MESSAGE_PREFIX | blockNumber | stakingModuleId |
        """
        tx = self.functions.pauseDeposits(
            block_number,
            staking_module_id,
            guardian_signature
        )
        logger.info({'msg': 'Build `pauseDeposits({}, {}, {})` tx.'.format(
            block_number,
            staking_module_id,
            guardian_signature,
        )})
        return tx

    def version(self, block_identifier: BlockIdentifier = 'latest') -> int:
        return 1


class DepositSecurityModuleContractV2(DepositSecurityModuleContract):
    abi_path = './interfaces/DepositSecurityModuleV2.json'

    def pause_deposits(  # Overwrite base pause_deposits
        self,
        block_number: int,
        guardian_signature: tuple[str, str],
    ) -> ContractFunction:
        """
        Pauses deposits for staking module given that both conditions are satisfied (reverts otherwise):

            1. The function is called by the guardian with index guardianIndex OR sig
                is a valid signature by the guardian with index guardianIndex of the data
                defined below.

            2. block.number - blockNumber <= pauseIntentValidityPeriodBlocks

        The signature, if present, must be produced for keccak256 hash of the following
        message (each component taking 32 bytes):

        | PAUSE_MESSAGE_PREFIX | blockNumber |
        """

        tx = self.functions.pauseDeposits(
            block_number,
            guardian_signature
        )
        logger.info({'msg': f'Build `pauseDeposits({block_number}, {guardian_signature})` tx.'})
        return tx

    def get_unvet_message_prefix(self, block_identifier: BlockIdentifier = 'latest') -> bytes:
        response = self.functions.UNVET_MESSAGE_PREFIX().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `UNVET_MESSAGE_PREFIX()`.', 'value': response.hex(), 'block_identifier': repr(block_identifier)})
        return response

    def unvet_signing_keys(
        self,
        block_number: int,
        block_hash: Hash32,
        staking_module_id: int,
        nonce: int,
        operator_ids: bytes,
        vetted_keys_by_operator: bytes,
        guardian_signature: tuple[str, str],
    ) -> ContractFunction:
        tx = self.functions.unvetSigningKeys(
            block_number,
            block_hash,
            staking_module_id,
            nonce,
            operator_ids,
            vetted_keys_by_operator,
            guardian_signature,
        )
        logger.info({'msg': 'Build `unvetSigningKeys({}, {}, {}, {}, {}, {})` tx.'.format(
            block_number,
            block_hash,
            staking_module_id,
            nonce,
            operator_ids,
            vetted_keys_by_operator,
            guardian_signature,
        )})
        return tx

    def is_deposits_paused(self, block_identifier: BlockIdentifier = 'latest') -> bool:
        """
        Returns if lido deposits are paused
        """
        response = self.functions.isDepositsPaused().call(block_identifier=block_identifier)
        logger.info({
            'msg': 'Call `isDepositsPaused()`.',
            'value': response,
            'block_identifier': repr(block_identifier),
        })
        return response

    def version(self, block_identifier: BlockIdentifier = 'latest') -> int:
        response = self.functions.VERSION().call(block_identifier=block_identifier)
        logger.info({
            'msg': 'Call `VERSION()`.',
            'value': response,
            'block_identifier': repr(block_identifier),
        })
        return response
