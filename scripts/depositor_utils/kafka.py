import json
from collections import defaultdict
from typing import List

from confluent_kafka import Consumer

from scripts.depositor_utils.logger import logger
from scripts.depositor_utils.prometheus import KAFKA_DEPOSIT_MESSAGES, KAFKA_PAUSE_MESSAGES
from scripts.depositor_utils.variables import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_SASL_USERNAME,
    KAFKA_SASL_PASSWORD,
    NETWORK,
    KAFKA_TOPIC
)


class KafkaMsgRecipient:
    """Simple kafka msg recipient"""

    def __init__(self):
        logger.info({'msg': 'Kafka initialize.'})
        self.messages = defaultdict(list)

        kafka_topic = f'{NETWORK}-{KAFKA_TOPIC}'

        self.kafka = Consumer({
            'client.id': f'{kafka_topic}-bot',
            'group.id': f'{kafka_topic}-group',
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'auto.offset.reset': 'earliest',
            'security.protocol': 'SASL_SSL',
            'session.timeout.ms': 6000,
            'sasl.mechanisms': "PLAIN",
            'sasl.username': KAFKA_SASL_USERNAME,
            'sasl.password': KAFKA_SASL_PASSWORD,
        })

        logger.info({'msg': f'Subscribe to "{kafka_topic}".'})
        self.kafka.subscribe([kafka_topic])

    def __del__(self):
        self.kafka.close()

    def update_messages(self):
        """Fetch new messages from kafka"""
        logger.info({'msg': 'Receive all messages from kafka.'})
        while True:
            msg = self.kafka.poll(timeout=1.0)

            if msg is None:
                # No messages in line
                break
            elif not msg.error():
                value = json.loads(msg.value())
                value = self._process_value(value)
                msg_type = value.get('type', None)
                self.messages[msg_type].append(value)
            else:
                logger.error({'msg': f'Kafka error: {msg.error()}'})

        logger.info({'msg': 'All messages received.'})

    def _process_value(self, value):
        return value


class DepositBotMsgRecipient(KafkaMsgRecipient):
    """
    Kafka msg recipient adapted for depositor bot.
    """
    def get_deposit_messages(self, block_number, deposit_root, keys_op_index) -> List[dict]:
        """
        Actualize deposit messages and return valid ones

        Deposit msg example
        {
          "type": "deposit",
          "depositRoot": "0xbc034415ccde0596f39095fd2d99c2fa1e335de3f70b34dcd78e2ab21fa0c5e8",
          "keysOpIndex": 16,
          "blockNumber": 5737984,
          "blockHash": "0x432e218931e9b94f0702ecb1b0d084c467a86b384767ce38c4fe164463070532",
          "guardianAddress": "0x43464Fe06c18848a2E2e913194D64c1970f4326a",
          "guardianIndex": 8,
          "signature": {
            "r": "0xc2235eb6983f80d19158f807d5d90d93abec52034ea7184bbf164ba211f00116",
            "s": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "_vs": "0x75354ffc9fb6e7a4b4c01c622661a1d0382ace8c4ff8024626e39ac1a6a613d0",
            "recoveryParam": 0,
            "v": 27
          },
          "app": {
            "version": "1.0.3",
            "name": "lido-council-daemon"
          }
        }
        """
        _guardian_addresses = []

        def _deposit_message_filter(msg):
            if msg.get('depositRoot', None) != deposit_root or msg.get('keysOpIndex') != keys_op_index:
                if msg.get('blockNumber', 0) < block_number:
                    return False

            # Every 50 block we waiting for new signatures even deposit_root wasn't changed
            # So we don't need signs older than 200
            elif msg.get('blockNumber', 0) < block_number - 200:
                return False

            # Filter duplicate messages from one guardian address
            guardian = msg.get('guardianAddress', None)
            if guardian not in _guardian_addresses:
                _guardian_addresses.append(guardian)
                return True

            return False

        self.messages['deposit'] = list(filter(_deposit_message_filter, self.messages['deposit']))

        return self.messages['deposit'][:]

    def get_pause_messages(self, block_number: int, blocks_till_pause_is_valid: int) -> List[dict]:
        """
        Actualize pause messages and return valid ones

        Pause msg example:
        {
            "blockHash": "0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c",
            "blockNumber": 5669490,
            "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
            "guardianIndex": 0,
            "signature": {
                "_vs": "0xd4933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
                "r": "0xbaa668505cd496caaf7117dd074338197200175057909ab73a04463656bdb0fa",
                "recoveryParam": 1,
                "s": "0x54933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
                "v": 28
            },
            "type": "pause"
        }
        """
        def _pause_message_filter(msg):
            if msg.get('blockNumber', 0) + blocks_till_pause_is_valid > block_number:
                return True

        self.messages['pause'] = list(filter(_pause_message_filter, self.messages['pause']))

        return self.messages['pause']

    def clear_pause_messages(self):
        self.messages['pause'] = []

    def _process_value(self, value):
        # Just logging
        logger.info({'msg': 'Send guardian statistic.'})
        guardian_address = value.get('guardianAddress', -1)
        daemon_version = value.get('app', {}).get('version', 'unavailable')

        logger.debug({'msg': 'Guardian message received.', 'data': value})
        if value.get('type', None) == 'deposit':
            KAFKA_DEPOSIT_MESSAGES.labels(guardian_address, daemon_version).inc()
        elif value.get('type', None) == 'pause':
            logger.warning({'msg': f'Received pause msg from: {guardian_address}'})
            KAFKA_PAUSE_MESSAGES.labels(guardian_address, daemon_version).inc()

        return super()._process_value(value)
