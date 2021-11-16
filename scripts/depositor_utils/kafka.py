import logging
from typing import List

from scripts.utils.kafka import KafkaMsgRecipient
from scripts.utils.metrics import KAFKA_DEPOSIT_MESSAGES, KAFKA_PING_MESSAGES

logger = logging.getLogger(__name__)


class DepositBotMsgRecipient(KafkaMsgRecipient):
    """
    Kafka msg recipient adapted for depositor bot.
    """
    msg_types_to_receive = ['deposit']

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
            if guardian in _guardian_addresses:
                return False

            _guardian_addresses.append(guardian)
            return True

        self.messages['deposit'] = list(filter(_deposit_message_filter, self.messages['deposit']))

        return self.messages['deposit'][:]

    def _process_value(self, value):
        # Just logging
        guardian_address = value.get('guardianAddress', -1)
        daemon_version = value.get('app', {}).get('version', 'unavailable')

        msg_type = value.get('type', None)
        logger.info({'msg': 'Guardian message received.', 'value': value, 'type': msg_type})
        if msg_type == 'deposit':
            KAFKA_DEPOSIT_MESSAGES.labels(guardian_address, daemon_version).inc()
        elif msg_type == 'ping':
            KAFKA_PING_MESSAGES.labels(guardian_address, daemon_version).inc()

        return super()._process_value(value)
