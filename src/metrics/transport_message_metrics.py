import logging

from metrics.metrics import KAFKA_DEPOSIT_MESSAGES, KAFKA_PING_MESSAGES
from transport.msg_schemas import DepositMessage


logger = logging.getLogger(__name__)


def message_metrics(msg: DepositMessage) -> bool:
    # Remove all ping messages, because we use them only for metrics
    msg_type = msg.get('type', None)
    logger.info({'msg': 'Guardian message received.', 'value': msg, 'type': msg_type})

    address, version = msg.get('guardianAddress'), msg.get('app', {}).get('version')

    if msg_type == 'deposit':
        KAFKA_DEPOSIT_MESSAGES.labels(address, version).inc()
        return True

    elif msg_type == 'ping':
        KAFKA_PING_MESSAGES.labels(address, version).inc()
        return False
