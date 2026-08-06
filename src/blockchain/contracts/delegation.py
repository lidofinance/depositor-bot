import logging

from eth_typing import ChecksumAddress
from web3.contract.contract import ContractFunction
from web3.types import BlockIdentifier

from blockchain.contracts.base_interface import ContractInterface
from utils.bytes import from_hex_string_to_bytes

logger = logging.getLogger(__name__)


class DelegationContract(ContractInterface):
    """An Execution Delegation Framework contract (LIP-37) the bot executes permissioned calls through.

    A delegation contract is a stable on-chain identity: protocol roles are granted to it, while a
    rotatable hot EOA — its *delegate* — performs the actual calls via `execute(target, data)`. The
    bot uses this for `TopUpGateway.topUp`, the only permissioned call it makes (`TOP_UP_ROLE`): the
    role sits on this contract instead of on the bot's key, so rotating the key is a delegate
    rotation by the contract's owner rather than an ACL change on TopUpGateway.

    Deposits, pause and unvet are deliberately NOT routed through here — DSM authorises those by
    guardian signatures in calldata, so wrapping them would only add gas and a failure mode.

    The same on-chain implementation also backs DSM guardians (see `GuardianContract`, which reads
    only `getDelegate()` to reverse-map Data Bus senders). They are kept apart because the bot uses
    them for unrelated purposes — one is our own execution identity, the other is a third party's.
    Worth unifying once the EDF ABI is published as a package.
    """

    abi_path = './interfaces/DelegationContract.json'

    def get_delegate(self, block_identifier: BlockIdentifier = 'latest') -> ChecksumAddress:
        """Returns the currently effective delegate EOA (zero address if revoked or terminated).

        During a cooldown-gated rotation the previous delegate stays effective until the nominated
        one matures, so only this address can `execute` right now.
        """
        response = self.functions.getDelegate().call(block_identifier=block_identifier)
        logger.debug(
            {
                'msg': 'Call `getDelegate()`.',
                'value': response,
                'delegation': self.address,
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    def is_terminated(self, block_identifier: BlockIdentifier = 'latest') -> bool:
        """Whether the contract has been terminated — irreversible, and `execute` reverts after it."""
        response = self.functions.isTerminated().call(block_identifier=block_identifier)
        logger.debug(
            {
                'msg': 'Call `isTerminated()`.',
                'value': response,
                'delegation': self.address,
                'block_identifier': repr(block_identifier),
            }
        )
        return response

    def wrap(self, call: ContractFunction) -> ContractFunction:
        """Re-targets a built call so it runs with this contract as `msg.sender`.

        Encodes the original call and returns `execute(originalTarget, calldata)`. The result is a
        normal ContractFunction, so gas estimation and the `transaction.check()` dry-run simulate the
        delegated call — which is what actually gets mined. Simulating the unwrapped call instead
        would revert with `AccessControlUnauthorizedAccount`, since the role is held by this contract
        and not by the bot's key.

        The call has already been assembled by the target contract's wrapper, so it is re-encoded
        here rather than rebuilt from arguments — argument encoding stays in one place.
        """
        target = self.w3.eth.contract(address=call.address, abi=call.contract_abi)
        calldata = from_hex_string_to_bytes(target.encode_abi(call.fn_name, call.args))
        logger.debug(
            {
                'msg': 'Wrap call into `execute()`.',
                'delegation': self.address,
                'target': call.address,
                'function': call.fn_name,
            }
        )
        return self.functions.execute(call.address, calldata)
