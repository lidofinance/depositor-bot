import abc
import logging
from collections import deque
from typing import Any, List, Optional

from schema import Schema, SchemaError

logger = logging.getLogger(__name__)


class BaseMessageProvider(abc.ABC):
    """Abstract message provider that receives messages and"""

    MAX_MESSAGES_RECEIVE = 1000

    def __init__(self, message_schema: Schema):
        self.message_schema = message_schema
        self._queue: deque[Any] = deque([])

    def get_messages(self) -> List[dict]:
        messages = []

        for _ in range(self.MAX_MESSAGES_RECEIVE):
            msg = self._fetch_message()

            if msg is None:
                break

            value = self._process_msg(msg)

            if value and self._is_valid(value):
                messages.append(value)

        return messages

    def _fetch_message(self) -> Optional[Any]:
        if not self._queue:
            messages = self._fetch_messages()
            if messages:
                self._queue.extend(messages)
        return None if not self._queue else self._queue.popleft()

    @abc.abstractmethod
    def _fetch_messages(self) -> List[Any]:
        raise NotImplementedError('Receive message from transport.')

    def _process_msg(self, msg: Any) -> Optional[dict]:
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
