import abc
import logging
from typing import Any

from prometheus_client import Gauge
from schema import Schema, SchemaError

logger = logging.getLogger(__name__)


class BaseMessageProvider(abc.ABC):
    """Abstract message provider that receives messages and"""

    MAX_MESSAGES_RECEIVE = 1000

    def __init__(self, message_schema: Schema):
        self.message_schema = message_schema

    def get_messages(self) -> list[dict]:
        """
        Fetches new messages, processes them, and filters out only the valid ones.

        Returns:
            List[Dict]: A list of processed and valid messages.
        """
        fetched = self._fetch_messages()
        self.fetched_messages_metric.set(len(fetched))
        processed = [self._process_msg(m) for m in fetched]
        self.processed_messages_metric.set(len(processed))
        valid = [msg for msg in processed if msg and self._is_valid(msg)]
        self.valid_messages_metric.set(len(valid))
        return valid

    @abc.abstractmethod
    def _fetch_messages(self) -> list:
        raise NotImplementedError('Receive message from transport.')

    def _process_msg(self, msg: Any) -> dict | None:
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

    @property
    @abc.abstractmethod
    def fetched_messages_metric(self) -> Gauge:
        raise NotImplementedError('fetched_messages_metric')

    @property
    @abc.abstractmethod
    def processed_messages_metric(self) -> Gauge:
        raise NotImplementedError('processed_messages_metric')

    @property
    @abc.abstractmethod
    def valid_messages_metric(self) -> Gauge:
        raise NotImplementedError('valid_messages_metric')
