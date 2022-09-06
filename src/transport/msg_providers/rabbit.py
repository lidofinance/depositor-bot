import json
import logging
from typing import Optional, List

import stomp
from schema import Schema

import variables
from transport.msg_providers.common import BaseMessageProvider
from variables import NETWORK, ENVIRONMENT

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

        self.conn = stomp.Connection([(variables.RABBIT_MQ_HOST, variables.RABBIT_MQ_PORT)])

        _self = self

        class STOMPListener(stomp.ConnectionListener):
            def on_message(self, frame):
                _self._receive_message_from_queue(frame.body)

        self.conn.set_listener(self.client, STOMPListener())

        self.conn.connect(variables.RABBIT_MQ_USERNAME, variables.RABBIT_MQ_PASSWORD, wait=True)

        for rk in routing_keys:
            self.conn.subscribe(destination=f'{NETWORK}-{ENVIRONMENT}/{rk}', id=self.client + rk, ack='auto')

    def __del__(self):
        self.conn.disconnect()

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
