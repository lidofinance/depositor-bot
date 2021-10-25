import json
import logging
from collections import defaultdict
from typing import List

from confluent_kafka import Consumer

from scripts.depositor_utils.prometheus import KAFKA_DEPOSIT_MESSAGES, KAFKA_PAUSE_MESSAGES
from scripts.depositor_utils.variables import KAFKA_BOOTSTRAP_SERVERS, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD


class KafkaMsgRecipient:
    """Simple kafka msg recipient"""

    def __init__(self):
        self.messages = defaultdict(list)

        self.kafka = Consumer({
            'client.id': 'depositor-bot',
            'group.id': 'goerli-defender-group',
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'auto.offset.reset': 'earliest',
            'security.protocol': 'SASL_SSL',
            'session.timeout.ms': 6000,
            'sasl.mechanisms': "PLAIN",
            'sasl.username': KAFKA_SASL_USERNAME,
            'sasl.password': KAFKA_SASL_PASSWORD,
        })

        self.kafka.subscribe(['goerli-defender'])

    def __del__(self):
        self.kafka.close()

    def update_messages(self):
        """Fetch new messages from kafka"""
        while True:
            msg = self.kafka.poll(timeout=1.0)

            if msg is None:
                # No messages in line
                break
            elif not msg.error():
                value = json.loads(msg.value())
                value = self._process_value(value)
                msg_type = value.get('type', None)

                if msg_type is not None:
                    self.messages[msg_type].append(value)
            else:
                logging.error(f'Kafka error: {msg.error()}')

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
            "blockHash": "0x1e35a82702964431eb9f7028ec8e0a226c95f98a2bdff7da10381a364c2c8ebd",
            "blockNumber": 5669490,
            "depositRoot": "0x939424bfa2af911f12bfa95cae4850ca5e5d9343f9cfea855902a4ad89983c37",
            "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
            "guardianIndex": 0,
            "keysOpIndex": 12,
            "signature": {
                "_vs": "0xffe6ca7d86118389c773ac647c6458324cae40c02e36c2982b1803d2db94195b",
                "r": "0xbf53de3c8f002a77c03114312e118798ee16ecc0293ea5cd80de59d08907514c",
                "recoveryParam": 1,
                "s": "0x7fe6ca7d86118389c773ac647c6458324cae40c02e36c2982b1803d2db94195b",
                "v": 28
            },
            "type": "deposit"
        }
        """
        def _deposit_message_filter(msg):
            if msg.get('depositRoot', None) != deposit_root or msg.get('keysOpIndex') != keys_op_index:
                if msg.get('blockNumber', 0) < block_number:
                    return False
            elif msg.get('blockNumber', 0) < block_number - 200:
                return False

            return True

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
        logging.info({'msg': 'Send guardian statistic'})
        guardian_address = value.get('guardianAddress', -1)
        if value.get('type', None) == 'deposit':
            KAFKA_DEPOSIT_MESSAGES.labels(guardian_address).inc()
        elif value.get('type', None) == 'pause':
            logging.warning(f'Received pause msg from: {guardian_address}')
            KAFKA_PAUSE_MESSAGES.labels(guardian_address).inc()

        return super()._process_value(value)
