from typing import Callable, Iterable, List

from transport.msg_providers.common import BaseMessageProvider
from transport.msg_types.common import BotMessage


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
        self._filters = filters

    def get_messages_and_actualize(self, *args: Callable[[BotMessage], bool]) -> Iterable[BotMessage]:
        """
        Fetches all messages from transports, applies both initial and additional filters, and updates the message list.

        Args:
            *args (Callable[[BotMessage], bool]): Additional filter functions to apply to the messages.

        Returns:
            Iterable[BotMessage]: A list of messages that pass all filters.
        """
        filters = self._filters
        filters.extend(args)

        messages = self.messages
        for transport in self._transports:
            messages.extend(transport.get_messages())
        for _filter in filters:
            messages = filter(_filter, messages)
        self.messages = list(messages)
        return self.messages

    def clear(self):
        """
        Clears all stored messages in the message list.
        """
        self.messages = []
