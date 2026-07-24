import logging

from blockchain.contracts.base_interface import ContractInterface
from web3.types import BlockIdentifier, EventData

logger = logging.getLogger(__name__)


class ConsolidationBusContract(ContractInterface):
    abi_path = './interfaces/ConsolidationBus.json'

    def get_requests_added_logs(self, from_block: BlockIdentifier, to_block: BlockIdentifier) -> list[EventData]:
        """`RequestsAdded(address indexed publisher, bytes batchData)` — the only event carrying pubkeys."""
        return list(self.events.RequestsAdded().get_logs(from_block=from_block, to_block=to_block))

    def get_requests_executed_logs(self, from_block: BlockIdentifier, to_block: BlockIdentifier) -> list[EventData]:
        """`RequestsExecuted(bytes32 indexed batchHash, uint256 feePaid)` — closes a batch (executed)."""
        return list(self.events.RequestsExecuted().get_logs(from_block=from_block, to_block=to_block))

    def get_batches_removed_logs(self, from_block: BlockIdentifier, to_block: BlockIdentifier) -> list[EventData]:
        """`BatchesRemoved(bytes32[] batchHashes)` — closes batches (admin removed)."""
        return list(self.events.BatchesRemoved().get_logs(from_block=from_block, to_block=to_block))

    def get_batch_info(self, batch_hash: bytes, block_identifier: BlockIdentifier = 'latest'):
        """`getBatchInfo(bytes32) -> (publisher, addedAt)`. publisher == 0x0 means the batch is not pending."""
        return self.functions.getBatchInfo(batch_hash).call(block_identifier=block_identifier)
