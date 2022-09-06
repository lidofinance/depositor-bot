import json
import logging
from typing import Optional

from confluent_kafka import Consumer as BaseConsumer
from schema import Schema

from transport.msg_providers.common import BaseMessageProvider
from variables import (
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


class KafkaMessageProvider(BaseMessageProvider):

    def __init__(self, message_schema: Schema, client: str):
        logger.info({'msg': 'Kafka initialize.'})

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

        super().__init__(client, message_schema)

    def __del__(self):
        self.kafka.close()

    def _receive_message(self) -> Optional[dict]:
        msg = self.kafka.poll(timeout=1)

        if msg is not None:
            if not msg.error():
                return msg.value()
            else:
                logger.error({'msg': f'Kafka error', 'error': str(msg.error())})

    def _process_msg(self, msg: str) -> Optional[dict]:
        try:
            value = json.loads(msg)
        except ValueError as error:
            # ignore not json msg
            logger.warning({'msg': 'Broken message in Kafka', 'value': str(msg), 'error': str(error)})
        else:
            return value
