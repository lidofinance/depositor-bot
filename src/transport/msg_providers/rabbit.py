import json
import logging
from typing import Optional, List

from schema import Schema

import variables
from transport.msg_providers.common import BaseMessageProvider
from transport.msg_providers.stomp.client import Client
from variables import NETWORK, KAFKA_TOPIC

logger = logging.getLogger(__name__)


class MessageType:
    PAUSE = 'pause'
    PING = 'ping'
    DEPOSIT = 'deposit'


class RabbitProvider(BaseMessageProvider):
    _queue: List[dict] = []

    def __init__(self, client: str, message_schema: Schema, routing_keys: List[str]):
        super().__init__(client, message_schema)

        logger.info({'msg': 'Rabbit initialize.'})

        self.client = Client(variables.RABBIT_MQ_HOST)

        self.client.connect(
            login=variables.RABBIT_MQ_USERNAME,
            passcode=variables.RABBIT_MQ_PASSWORD,
        )

        def on_message(frame):
            self._receive_message_from_queue(frame.body)

        for rk in routing_keys:
            self.client.subscribe(f'/exchange/{NETWORK}-{KAFKA_TOPIC}/{rk}', callback=on_message)

    def __del__(self):
        self.client.disconnect()

    def _receive_message(self) -> Optional[dict]:
        try:
            return self._queue.pop()
        except IndexError:
            return None

    def _receive_message_from_queue(self, body):
        self._queue.append(body)

    def _process_msg(self, msg: str) -> Optional[dict]:
        try:
            value = json.loads(msg)
        except ValueError as error:
            # ignore not json msg
            logger.warning({'msg': 'Broken message in Kafka', 'value': str(msg), 'error': str(error)})
        else:
            return value
