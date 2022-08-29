import abc
import json
import logging
from typing import List, Any

from schema import Schema, SchemaError


logger = logging.getLogger(__name__)


class BaseMessageProvider(abc.ABC):
    """Abstract message provider that receives messages and"""
    MAX_MESSAGES_RECEIVE = 1000

    def __init__(self, message_schema: Schema):
        self.message_schema = message_schema

    def get_messages(self) -> List[dict]:
        messages = []

        tmp = self._receive_message()

        for i in range(self.MAX_MESSAGES_RECEIVE):
            # msg = self._receive_message()
            try:
                msg = next(tmp)
                msg = json.dumps(msg)
            except StopIteration:
                break

            if msg is None:
                break

            value = self._process_msg(msg)

            if value and self._is_valid(value):
                messages.append(value)

        return messages

    def _receive_message(self) -> Any:
        raise NotImplemented("Receive message from transport.")

    def _process_msg(self, msg: Any) -> dict:
        # Overwrite this method to add msg serialization.
        # Return None if message is not serializable
        return msg

    def _is_valid(self, msg: dict):
        try:
            self.message_schema.validate(msg)
        except SchemaError as error:
            logger.warning({'msg': 'Invalid message.', 'value': str(msg), 'error': str(error)})
            return False

        return True
