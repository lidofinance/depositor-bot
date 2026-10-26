from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def stub_databus():
    """Bots always build a Data Bus provider; tests feed messages into MessageStorage directly instead."""
    provider_cls = MagicMock()
    provider_cls.return_value.get_messages.return_value = []
    transport_w3 = provider_cls.create_onchain_transport_w3.return_value
    transport_w3.eth.get_balance.return_value = 0
    transport_w3.eth.chain_id = 100
    with (
        patch('bots.depositor.OnchainTransportProvider', provider_cls),
        patch('bots.pauser.OnchainTransportProvider', provider_cls),
        patch('bots.unvetter.OnchainTransportProvider', provider_cls),
    ):
        yield provider_cls
