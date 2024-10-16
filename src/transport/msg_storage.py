from typing import Any, Callable, Iterable, List

from blockchain.typings import Web3
from metrics.metrics import GUARDIAN_BALANCE
from transport.msg_providers.common import BaseMessageProvider


def _chain_id_to_web3_mapping(clients: Iterable[Web3]):
    chain_id_web3 = dict()
    for w3_client in clients:
        chain = w3_client.eth.chain_id
        chain_id_web3[chain] = w3_client
    return chain_id_web3


class MessageStorage:
    messages: List = []

    """Fetches all messages, filter them and storing"""

    def __init__(self, transports: List[BaseMessageProvider], filters: List[Callable], web3_clients: Iterable[Web3] = ()):
        """
        transports - List of objects with working get_messages method.
        filters - functions that would be applied to messages when they are received. (That would need only one check)
        """
        self._transports = transports
        self._filters = filters
        self._chain_id_to_web3 = _chain_id_to_web3_mapping(web3_clients)

    def receive_messages(self) -> Iterable[dict]:
        """Fetch all messages from transport and filter them"""
        for transport in self._transports:
            messages = transport.get_messages()

            for _filter in self._filters:
                messages = filter(_filter, messages)

            self.messages.extend(messages)

        self._update_metrics()
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

    def _update_metrics(self):
        addresses = set([m.get('guardianAddress') for m in self.messages])
        for address in addresses:
            for chain_id, client in self._chain_id_to_web3.items():
                balance = client.eth.get_balance(address)
                GUARDIAN_BALANCE.labels(address=address, chain_id=str(chain_id)).set(balance)
