from typing import Any, Callable, Iterable, List, Optional

from transport.msg_providers.common import BaseMessageProvider
from transport.msg_types.common import get_messages_sign_filter


class MessageStorage:
    messages: List = []

    """Fetches all messages, filter them and storing"""

    def __init__(self, transports: List[BaseMessageProvider], filters: List[Callable], prefix_provider: Optional[Callable] = None):
        """
        transports - List of objects with working get_messages method.
        filters - functions that would be applied to messages when they are received. (That would need only one check)
        """
        self._transports = transports
        self._filters = filters
        self._prefix_provider = prefix_provider

    def receive_messages(self) -> Iterable[dict]:
        """Fetch all messages from transport and filter them"""
        filters = self._filters
        if self._prefix_provider:
            prefix = self._prefix_provider()
            filters.append(get_messages_sign_filter(prefix))

        for transport in self._transports:
            messages = transport.get_messages()

            for _filter in self._filters:
                messages = filter(_filter, messages)

            self.messages.extend(messages)

        return self.messages

    def get_messages(self, actualize_rule: Callable[[Any], bool]) -> List[Any]:
        """
        actualize_rule - is filter that filters all outdated messages
        """
        self.receive_messages()
        self.messages = list(filter(actualize_rule, self.messages))
        return self.messages

    def clear(self):
        self.messages = []
