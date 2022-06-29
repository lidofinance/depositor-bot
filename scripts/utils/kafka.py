import json
import logging
from collections import defaultdict

from confluent_kafka import Consumer as BaseConsumer

from scripts.utils.variables import (
    KAFKA_BROKER_ADDRESS_1,
    KAFKA_USERNAME,
    KAFKA_PASSWORD,
    KAFKA_TOPIC,
    NETWORK,
)

logger = logging.getLogger(__name__)


class Consumer(BaseConsumer):
    """Lifehack for tests. We can't monkey patch side binaries"""
    def poll(self, timeout=None):
        return super().poll(timeout)


class KafkaMsgRecipient:
    """
    Simple kafka msg recipient
    """

    # Will store only next types of messages
    # If empty will store all types
    msg_types_to_receive: list = []

    def __init__(self, client: str):
        logger.info({'msg': 'Kafka initialize.'})
        self.messages = defaultdict(list)

        kafka_topic = f'{NETWORK}-{KAFKA_TOPIC}'

        self.kafka = Consumer({
            'client.id': kafka_topic + f'-{client}-client',
            'group.id': kafka_topic + f'-{client}-group',
            'bootstrap.servers': KAFKA_BROKER_ADDRESS_1,
            'auto.offset.reset': 'earliest',
            'security.protocol': 'SASL_SSL',
            'session.timeout.ms': 240000,
            'sasl.mechanisms': 'PLAIN',
            'sasl.username': KAFKA_USERNAME,
            'sasl.password': KAFKA_PASSWORD,
        })

        logger.info({'msg': f'Subscribe to "{kafka_topic}".'})
        self.kafka.subscribe([kafka_topic])

    def __del__(self):
        self.kafka.close()

    def update_messages(self):
        """Fetch new messages from kafka"""
        logger.info({'msg': 'Receive all messages from kafka.'})
        while True:
            msg = self.kafka.poll(timeout=1)

            if msg is None:
                # No messages in line
                break
            elif not msg.error():
                message = msg.value()

                try:
                    value = json.loads(message)
                except ValueError as error:
                    # ignore not json msg
                    logger.warning({'msg': 'Broken message in Kafka', 'value': message, 'error': str(error)})
                else:
                    value = self._process_value(value)
                    msg_type = value.get('type', None)

                    if not self.msg_types_to_receive or msg_type in self.msg_types_to_receive:
                        self.messages[msg_type].insert(0, value)
            else:
                logger.error({'msg': f'Kafka error', 'error': str(msg.error())})

        logger.info({'msg': 'All messages received.'})

    def _process_value(self, value):
        """OverWrite this method to add msg handling"""
        return value
