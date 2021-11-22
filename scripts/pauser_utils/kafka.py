import logging
from typing import List

from scripts.utils.kafka import KafkaMsgRecipient
from scripts.utils.metrics import KAFKA_PAUSE_MESSAGES


logger = logging.getLogger(__name__)


class PauseBotMsgRecipient(KafkaMsgRecipient):
    """
    Kafka msg recipient adapted for depositor bot.
    """
    msg_types_to_receive = ['pause']

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

        return self.messages['pause'][:]

    def clear_pause_messages(self):
        self.messages['pause'] = []

    def _process_value(self, value):
        # Just logging
        guardian_address = value.get('guardianAddress', -1)
        daemon_version = value.get('app', {}).get('version', 'unavailable')

        msg_type = value.get('type', None)
        logger.debug({'msg': 'Guardian message received.', 'value': value, 'type': msg_type})

        if msg_type == 'pause':
            logger.warning({'msg': f'Received pause msg.', 'value': value, 'address': guardian_address})
            KAFKA_PAUSE_MESSAGES.labels(guardian_address, daemon_version).inc()

        return super()._process_value(value)
