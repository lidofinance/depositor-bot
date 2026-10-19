from unittest.mock import patch

import pytest

import variables
from main import main


@pytest.mark.unit
@pytest.mark.parametrize(
    'address,endpoints',
    [
        (None, ['https://rpc.gnosis.example']),
        ('0x37De961D6bb5865867aDd416be07189D2Dd960e6', []),
    ],
)
def test_main_requires_databus_config(address, endpoints):
    with (
        patch.object(variables, 'ONCHAIN_TRANSPORT_ADDRESS', address),
        patch.object(variables, 'ONCHAIN_TRANSPORT_RPC_ENDPOINTS', endpoints),
        patch('main.start_pulse_server') as pulse,
        pytest.raises(ValueError, match='Data Bus is the only message transport'),
    ):
        main('pauser')
    pulse.assert_not_called()
