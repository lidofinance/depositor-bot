import datetime
import json
import logging
import time
from typing import List, Optional

import variables
from schema import Schema
from transport.msg_providers.common import BaseMessageProvider
from transport.msg_providers.stomp.client import Client

logger = logging.getLogger(__name__)


class MessageType:
    PAUSE = 'pause'
    PING = 'ping'
    DEPOSIT = 'deposit'
    UNVET = 'unvet'


class RabbitProvider(BaseMessageProvider):
    _queue: List[dict] = []
    last_reconnect_dt = datetime.datetime.now()
    connection = True

    def __init__(self, client: str, message_schema: Schema, routing_keys: List[str]):
        super().__init__(client, message_schema)

        logger.info({'msg': 'Rabbit initialize.'})
        self.routing_keys = routing_keys
        self._create_client()

    def _create_client(self):
        logger.info({'msg': 'Create StompClient.'})
        self.client = Client(
            variables.RABBIT_MQ_URL,
            on_close=self._recreate_client,
        )
        self.client.connect(
            login=variables.RABBIT_MQ_USERNAME,
            passcode=variables.RABBIT_MQ_PASSWORD,
            host='/',
            timeout=10,
        )
        self._subscribe()

    def _subscribe(self):
        def on_message(frame):
            self._receive_message_from_queue(frame.body)

        while self.client.opened:
            if self.client.connected:
                for rk in self.routing_keys:
                    self.client.subscribe(f'/amq/queue/{rk}', callback=on_message)
                break
            time.sleep(1)

    def _recreate_client(self):
        # Make sure client creating won't be instantly
        time.sleep(5)
        logger.error({'msg': 'Trying to reconnect to client.'})
        current_dt = datetime.datetime.now()
        if current_dt - self.last_reconnect_dt < datetime.timedelta(seconds=5):
            self.connection = False
            logger.error({'msg': '2 failed reconnections in 5 seconds.'})

        self.last_reconnect_dt = current_dt

        logger.warning({'msg': 'Trying to reconnect to WebSocket.'})
        time.sleep(2)
        self._create_client()

    def __del__(self):
        self.client.disconnect()

    def _receive_message(self) -> Optional[dict]:
        if not self.connection:
            raise ConnectionError('Connection RabbitMQ was lost.')

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
            return None

        return value
