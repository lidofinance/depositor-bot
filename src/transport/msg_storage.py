from typing import Callable, List

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
        self._filter = lambda x: all(f(x) for f in filters)

    def get_messages_and_actualize(self, actualize_filter: Callable[[BotMessage], bool]) -> list[BotMessage]:
        """
        Fetches all messages from each transport, applies filtering, and updates the message list.

        This method retrieves messages from all transports associated with the instance and filters them
        based on both the instance’s `_filter` function and an additional `actualize_filter` function
        provided as an argument. The filtered messages are stored in the instance's `messages` attribute.

        Args:
            actualize_filter (Callable[[BotMessage], bool]): A function that takes a `BotMessage` as an argument
                                                                and returns `True` if the message should be included
                                                                after filtering; otherwise, `False`.

        Returns:
            list[BotMessage]: A list of `BotMessage` objects that pass both the instance filter and the
                                `actualize_filter` criteria.
        """
        messages = self.messages
        for transport in self._transports:
            messages.extend(transport.get_messages())
        self.messages = list(filter(lambda x: self._filter(x) and actualize_filter(x), messages))
        return self.messages

    def clear(self):
        """
        Clears all stored messages in the message list.
        """
        self.messages = []
