from typing import Any, Callable, Iterable, List

from transport.msg_providers.common import BaseMessageProvider


class MessageStorage:
    messages: List = []

    """Fetches all messages, filter them and storing"""

    def __init__(self, transports: List[BaseMessageProvider], filters: List[Callable]):
        """
        transports - List of objects with working get_messages method.
        filters - functions that would be applied to messages when they are received. (That would need only one check)
        """
        self._transports = transports
        self._filters = filters

    def receive_messages(self, caller_filters: List[Callable[[Any], bool]] = ()) -> Iterable[dict]:
        """Fetch all messages from transport and filter them"""
        filters = self._filters
        filters.extend(caller_filters)

        for transport in self._transports:
            messages = transport.get_messages()

            for _filter in filters:
                messages = filter(_filter, messages)

            self.messages.extend(messages)

        return self.messages

    def get_messages(self, caller_filters: List[Callable[[Any], bool]]) -> List[Any]:
        """
        actualize_rule - is filter that filters all outdated messages
        """
        self.receive_messages(caller_filters=caller_filters)
        return self.messages

    def clear(self):
        self.messages = []
