import logging
from functools import lru_cache

from eth_typing import ChecksumAddress, Hash32
from web3.contract.contract import ContractFunction
from web3.types import BlockIdentifier

from blockchain.contracts.base_interface import ContractInterface

logger = logging.getLogger(__name__)

# A guardian signature as passed to the DSM.
# - DSMv4: the compact ECDSA pair ``(r, _vs)`` recovered on-chain to the guardian EOA.
# - DSMv5: ``(guardian_contract, signature_bytes)`` where signature_bytes is the 65-byte ``r||s||v``
#   blob verified via the guardian contract's ERC-1271 ``isValidSignature`` (LIP-37 / EDF).
GuardianSignature = tuple[str, str] | tuple[str, bytes]


class DepositSecurityModuleContract(ContractInterface):
    abi_path = './interfaces/DepositSecurityModuleV4.json'

    @lru_cache(maxsize=1)
    def get_guardian_quorum(self, block_identifier: BlockIdentifier = 'latest') -> int:
        """Returns number of valid guardian signatures required to vet (depositRoot, nonce) pair."""
        response = self.functions.getGuardianQuorum().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getGuardianQuorum()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    @lru_cache(maxsize=1)
    def get_guardians(self, block_identifier: BlockIdentifier = 'latest') -> list[ChecksumAddress]:
        """Returns guardian committee member list."""
        response = self.functions.getGuardians().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getGuardians()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    @lru_cache(maxsize=1)
    def get_attest_message_prefix(self, block_identifier: BlockIdentifier = 'latest') -> bytes:
        response = self.functions.ATTEST_MESSAGE_PREFIX().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `ATTEST_MESSAGE_PREFIX()`.', 'value': response.hex(), 'block_identifier': repr(block_identifier)})
        return response

    def is_min_deposit_distance_passed(self, staking_module_id: int, block_identifier: BlockIdentifier = 'latest') -> bool:
        """Whether the global min deposit block distance has passed since the last deposit.

        Standalone view of just the distance condition inside `canDeposit` (point 5 of
        `depositBufferedEther`): `block.number - getLastDepositBlock() >= minDepositBlockDistance`.
        The last deposit block is global (a deposit to any module advances it), so this gates every
        module. Used to tell a transient distance block apart from a permanent one.
        """
        response = self.functions.isMinDepositDistancePassed(staking_module_id).call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': f'Call `isMinDepositDistancePassed({staking_module_id})`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    def deposit_buffered_ether(
        self,
        block_number: int,
        block_hash: Hash32,
        deposit_root: Hash32,
        staking_module_id: int,
        nonce: int,
        guardian_signatures: tuple[GuardianSignature, ...],
    ) -> ContractFunction:
        """
        Calls STAKING_ROUTER.deposit(stakingModuleId, "") (deposit calldata is always empty in DSMv4).

        Reverts if any of the following is true:
        1. IDepositContract.get_deposit_root() != depositRoot.
        2. StakingRouter.getStakingModuleNonce() != nonce.
        3. quorum == 0 or the number of guardian signatures is less than the quorum.
        4. The module is not active.
        5. block.number - StakingModule.getLastDepositBlock() < minDepositBlockDistance.
        6. blockHash is zero or blockhash(blockNumber) != blockHash.
        7. Deposits are paused.
        8. An invalid or non-guardian signature received.

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
            guardian_signatures,
        )
        logger.info(
            {
                'msg': f'Build `depositBufferedEther({block_number}, {block_hash}, {deposit_root}, {staking_module_id}, '
                f'{nonce}, {guardian_signatures})` tx.'  # noqa
            }
        )
        return tx

    @lru_cache(maxsize=1)
    def get_pause_message_prefix(self, block_identifier: BlockIdentifier = 'latest') -> bytes:
        response = self.functions.PAUSE_MESSAGE_PREFIX().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `PAUSE_MESSAGE_PREFIX()`.', 'value': response.hex(), 'block_identifier': repr(block_identifier)})
        return response

    @lru_cache(maxsize=1)
    def get_pause_intent_validity_period_blocks(self, block_identifier: BlockIdentifier = 'latest') -> int:
        """Returns current `pauseIntentValidityPeriodBlocks` contract parameter (see `pauseDeposits`)."""
        response = self.functions.getPauseIntentValidityPeriodBlocks().call(block_identifier=block_identifier)
        logger.info({'msg': 'Call `getPauseIntentValidityPeriodBlocks()`.', 'value': response, 'block_identifier': repr(block_identifier)})
        return response

    def pause_deposits(
        self,
        block_number: int,
        guardian_signature: GuardianSignature,
    ) -> ContractFunction:
        """
        Pauses deposits given that both conditions are satisfied (reverts otherwise):

                1. The function is called by the guardian with index guardianIndex OR sig
                        is a valid signature by the guardian with index guardianIndex of the data
                        defined below.

                2. block.number - blockNumber <= pauseIntentValidityPeriodBlocks

        The signature, if present, must be produced for keccak256 hash of the following
        message (each component taking 32 bytes):

        | PAUSE_MESSAGE_PREFIX | blockNumber |
        """
        tx = self.functions.pauseDeposits(block_number, guardian_signature)
        logger.info({'msg': f'Build `pauseDeposits({block_number}, {guardian_signature})` tx.'})
        return tx

    @lru_cache(maxsize=1)
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
        guardian_signature: GuardianSignature,
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
        logger.info(
            {
                'msg': f'Build `unvetSigningKeys({block_number}, {block_hash}, {staking_module_id}, {nonce}, '
                f'{operator_ids}, {vetted_keys_by_operator}, {guardian_signature})` tx.'  # noqa
            }
        )
        return tx

    def is_deposits_paused(self, block_identifier: BlockIdentifier = 'latest') -> bool:
        """
        Returns if lido deposits are paused
        """
        response = self.functions.isDepositsPaused().call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': 'Call `isDepositsPaused()`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    @lru_cache(maxsize=1)
    def get_max_operators_per_unvetting(self, block_identifier: BlockIdentifier = 'latest') -> int:
        response = self.functions.getMaxOperatorsPerUnvetting().call(block_identifier=block_identifier)
        logger.info(
            {
                'msg': 'Call `getMaxOperatorsPerUnvetting()`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    @lru_cache(maxsize=1)
    def version(self, block_identifier: BlockIdentifier = 'latest') -> int:
        response = self.functions.VERSION().call(block_identifier=block_identifier)

        logger.info(
            {
                'msg': 'Call `VERSION()`.',
                'value': response,
                'block_identifier': repr(block_identifier),
            }
        )
        return response


class DepositSecurityModuleContractV5(DepositSecurityModuleContract):
    """DSM v5 (LIP-37 / Execution Delegation Framework).

    The read interface and the argument *order* of deposit/pause/unvet are unchanged from v4, so the
    inherited methods forward as-is. What changes is the guardian-signature encoding: each signature
    is now a ``(guardian_contract, signature_bytes)`` tuple (the ``GuardianSignature`` struct) instead
    of the compact ``(r, _vs)`` pair, and the signed digest binds the guardian address. Callers build
    the correct shape based on the DSM version; only the ABI needs to differ here.
    """

    abi_path = './interfaces/DepositSecurityModuleV5.json'
