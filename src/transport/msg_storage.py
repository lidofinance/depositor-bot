import logging
from typing import Any, Callable, List

from metrics.metrics import UNEXPECTED_EXCEPTIONS
from transport.msg_providers.common import BaseMessageProvider
from transport.msg_types.common import BotMessage

logger = logging.getLogger(__name__)


class MessageStorage:
    """
    A storage class for managing and filtering messages fetched from various transports.

    Attributes:
        messages (List): A list storing all messages after filtering.
    """

    messages: List = []

    def __init__(self, transports: List[BaseMessageProvider], filters: List[Callable]):
        """
        Initializes the MessageStorage with a list of transports and filters.

        Args:
            transports (List[BaseMessageProvider]): A list of transport objects that provide a `get_messages` method
                                                   for fetching messages.
            filters (List[Callable]): A list of filter functions that take a message as input and return a boolean,
                                      used to filter messages when they are received.
        """
        self._transports = transports
        self._filter = lambda x: all(f(x) for f in filters)

    def get_messages_and_actualize(self, actualize_filter: Callable[[BotMessage], bool]) -> list[BotMessage]:
        """
        Fetches all messages from each transport, applies filtering, and updates the message list.

        A message whose filter raises is dropped, not retained — otherwise it aborts every later cycle.

        Args:
            actualize_filter (Callable[[BotMessage], bool]): A function that takes a `BotMessage` as an argument
                                                                and returns `True` if the message should be included
                                                                after filtering; otherwise, `False`.

        Returns:
            list[BotMessage]: A list of `BotMessage` objects that pass both the instance filter and the
                                `actualize_filter` criteria.
        """
        messages = list(self.messages)
        for transport in self._transports:
            messages.extend(msg for msg in transport.get_messages() if self._passes(self._filter, msg))
        self.messages = [msg for msg in messages if self._passes(actualize_filter, msg)]
        return self.messages

    @staticmethod
    def _passes(message_filter: Callable[[Any], bool], message: Any) -> bool:
        try:
            return bool(message_filter(message))
        except Exception as error:
            UNEXPECTED_EXCEPTIONS.labels('malformed_message').inc()
            logger.warning({'msg': 'Message dropped, filter raised.', 'value': message, 'error': str(error)})
            return False

    def clear(self):
        """
        Clears all stored messages in the message list.
        """
        self.messages = []
