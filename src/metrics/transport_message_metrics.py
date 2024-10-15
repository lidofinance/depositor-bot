import logging
from typing import TypedDict

from blockchain.typings import Web3
from metrics.metrics import DEPOSIT_MESSAGES, GUARDIAN_BALANCE, PAUSE_MESSAGES, PING_MESSAGES, UNVET_MESSAGES
from transport.msg_providers.rabbit import MessageType

logger = logging.getLogger(__name__)


def _chain_id_to_web3_mapping(clients: list[Web3]):
    chain_id_web3 = {}
    for w3_client in clients:
        chain = w3_client.eth.chain_id
        chain_id_web3[chain] = w3_client
    return chain_id_web3


def message_metrics_curried(clients: list[Web3]):
    chain_id_to_clients = _chain_id_to_web3_mapping(clients)

    def message_metrics_filter(msg: TypedDict) -> bool:
        """
        Processes guardian messages and updates Prometheus metrics based on the message type.
        Returns True for valid message types to allow further processing, and False for messages
        that should be filtered (such as PING messages).

        Args:
            msg: A dictionary containing message details.

        Returns:
            bool: True if the message should be processed, False otherwise.
        """
        msg_type = msg.get('type')
        logger.info({'msg': 'Guardian message received.', 'value': msg, 'type': msg_type})

        address = msg.get('guardianAddress')
        version = msg.get('app', {}).get('version')
        transport = msg.get('transport', '')
        chain_id = msg.get('chain_id', '')
        staking_module_id = msg.get('stakingModuleId', -1)

        for chain_id, client in chain_id_to_clients.items():
            balance = client.eth.get_balance(address)
            GUARDIAN_BALANCE.labels(address=address, chain_id=str(chain_id)).set(balance)

        metrics_map = {
            MessageType.PAUSE: PAUSE_MESSAGES,
            MessageType.DEPOSIT: DEPOSIT_MESSAGES,
            MessageType.UNVET: UNVET_MESSAGES,
        }

        if msg_type in metrics_map:
            metrics_map[msg_type].labels(
                address=address,
                module_id=staking_module_id,
                version=version,
                transport=transport,
                chain_id=chain_id,
            ).inc()
            return True

        if msg_type == MessageType.PING:
            PING_MESSAGES.labels(address=address, version=version, transport=transport, chain_id=chain_id).inc()
            return False

        logger.warning({'msg': 'Received unexpected msg type.', 'value': msg, 'type': msg_type})
        return False

    return message_metrics_filter
