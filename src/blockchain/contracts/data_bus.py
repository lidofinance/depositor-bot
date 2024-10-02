import logging

from blockchain.contracts.base_interface import ContractInterface
from web3.contract.contract import ContractFunction

logger = logging.getLogger(__name__)


class DataBusContract(ContractInterface):
    abi_path = './interfaces/DataBusContract.json'

    def send_message(self, event_id: bytes, mes: bytes) -> ContractFunction:
        """
        Build send message transaction to Data Bus contract
        """
        tx = self.functions.send_message(event_id, mes)
        logger.info({'msg': f'Build `send_message({event_id.hex()}, {mes.hex()})` tx.'})
        return tx
