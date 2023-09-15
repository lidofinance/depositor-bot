import logging

from metrics.metrics import DEPOSIT_MESSAGES, PING_MESSAGES, PAUSE_MESSAGES
from transport.msg_providers.rabbit import MessageType
from transport.msg_schemas import DepositMessage


logger = logging.getLogger(__name__)


def message_metrics_filter(msg: DepositMessage) -> bool:
    msg_type = msg.get('type', None)
    logger.info({'msg': 'Guardian message received.', 'value': msg, 'type': msg_type})

    address, version = msg.get('guardianAddress'), msg.get('app', {}).get('version')

    if msg_type == MessageType.PAUSE:
        PAUSE_MESSAGES.labels(address, version).inc()
        return True

    if msg_type == MessageType.DEPOSIT:
        DEPOSIT_MESSAGES.labels(address, version).inc()
        return True

    elif msg_type == MessageType.PING:
        # Filter all ping messages, because we use them only for metrics
        PING_MESSAGES.labels(address, version).inc()
        return False

    logger.warning({'msg': 'Received unexpected msg type.', 'value': msg, 'type': msg_type})
