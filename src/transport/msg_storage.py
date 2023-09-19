from typing import Callable, Iterable, List

from transport.msg_providers.common import BaseMessageProvider
from transport.msg_schemas import DepositMessage


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

    def _receive_messages(self) -> Iterable[dict]:
        """Fetch all messages from transport and filter them"""
        for transport in self._transports:
            messages = transport.get_messages()

            for _filter in self._filters:
                messages = filter(_filter, messages)

            self.messages.extend(messages)

        return self.messages

    def get_messages(self, actualize_rule: Callable[[DepositMessage], bool]) -> List[dict]:
        """
        actualize_rule - is filter that filters all outdated messages
        """
        self._receive_messages()
        self.messages = list(filter(actualize_rule, self.messages))
        return self.messages

    def clear(self):
        self.messages = []
