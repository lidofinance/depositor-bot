import logging

from eth_typing import ChecksumAddress
from web3.types import BlockIdentifier

from blockchain.contracts.base_interface import ContractInterface

logger = logging.getLogger(__name__)


class GuardianContract(ContractInterface):
    """A DSM guardian under the LIP-37 Execution Delegation Framework.

    Guardians are no longer EOAs but delegation contracts (ERC-1271). The hot key that signs
    council messages and posts them on the Data Bus is the guardian's *delegate* EOA, which the
    owner can rotate, revoke, or terminate. Only the single `getDelegate()` view is used here — the
    bot resolves a Data Bus message's sender (delegate EOA) back to its guardian contract through it.
    """

    abi_path = './interfaces/Guardian.json'

    def get_delegate(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        """Returns the guardian's *currently effective* delegate EOA (zero address if none).

        During a cooldown-gated rotation the previous delegate stays effective until the new one
        matures, and the zero address is returned once the delegate is revoked or the contract is
        terminated. Reading this fresh each cycle is therefore what makes stale-delegate messages
        fail closed.
        """
        response = self.functions.getDelegate().call(block_identifier=block_identifier)
        logger.debug(
            {
                'msg': 'Call `getDelegate()`.',
                'value': response,
                'guardian': self.address,
                'block_identifier': repr(block_identifier),
            }
        )
        return response
