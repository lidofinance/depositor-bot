import logging
from typing import TypedDict

from metrics.metrics import DEPOSIT_MESSAGES, PAUSE_MESSAGES, PING_MESSAGES, UNVET_MESSAGES
from transport.msg_providers.rabbit import MessageType

logger = logging.getLogger(__name__)


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

    guardian_contract = msg.get('guardianAddress')
    sender_eoa = msg.get('guardianDelegate') or guardian_contract
    version = msg.get('app', {}).get('version')
    transport = msg.get('transport', '')
    chain_id = msg.get('chain_id', '')
    staking_module_id = msg.get('stakingModuleId', -1)

    metrics_map = {
        MessageType.PAUSE: PAUSE_MESSAGES,
        MessageType.DEPOSIT: DEPOSIT_MESSAGES,
        MessageType.UNVET: UNVET_MESSAGES,
    }

    if msg_type in metrics_map:
        metrics_map[msg_type].labels(
            address=sender_eoa,
            guardian=guardian_contract,
            module_id=staking_module_id,
            version=version,
            transport=transport,
            chain_id=chain_id,
        ).inc()
        return True

    if msg_type == MessageType.PING:
        PING_MESSAGES.labels(address=sender_eoa, guardian=guardian_contract, version=version, transport=transport, chain_id=chain_id).inc()
        return False

    logger.warning({'msg': 'Received unexpected msg type.', 'value': msg, 'type': msg_type})
    return False
