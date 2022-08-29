import json
import logging
import threading
from typing import Optional, List

import pika
from schema import Schema

from transport.msg_providers.common import BaseMessageProvider
from variables import NETWORK, ENVIRONMENT

logger = logging.getLogger(__name__)


class MessageType:
    PAUSE = 'pause'
    PING = 'ping'
    DEPOSIT = 'deposit'


class RabbitProvider(BaseMessageProvider):
    _queue: List[dict] = []

    def __init__(self, message_schema: Schema, routing_keys: List[str]):
        logger.info({'msg': 'Rabbit initialize.'})

        self.rabbit = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        self.channel = self.rabbit.channel()

        exchange = f'{NETWORK}-{ENVIRONMENT}'

        result = self.channel.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue

        for rk in routing_keys:
            self.channel.queue_bind(exchange=exchange, queue=queue_name, routing_key=rk)

        self.channel.basic_consume(queue=queue_name, on_message_callback=self._receive_message_from_queue, auto_ack=True)

        thread = threading.Thread(target=self.channel.start_consuming, daemon=True)
        thread.start()

        super().__init__(message_schema)

    def __del__(self):
        self.rabbit.close()

    def _receive_message(self) -> Optional[dict]:
        try:
            return self._queue.pop()
        except IndexError:
            return None

    def _receive_message_from_queue(self, ch, method, properties, body):
        self._queue.append(body)

    def _process_msg(self, msg: str) -> Optional[dict]:
        try:
            value = json.loads(msg)
        except ValueError as error:
            # ignore not json msg
            logger.warning({'msg': 'Broken message in Kafka', 'value': str(msg), 'error': str(error)})
        else:
            return value
