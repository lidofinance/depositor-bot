from unittest.mock import patch

import pytest

from blockchain.beacon_state.constants import FAR_FUTURE_EPOCH
from providers.consensus import ConsensusClient


def _client() -> ConsensusClient:
    return ConsensusClient(['http://cl'], request_timeout=1, retry_total=0, retry_backoff_factor=0)


@pytest.mark.unit
def test_get_gloas_fork_epoch_reads_cl_spec():
    cl = _client()
    with patch.object(cl, '_get', return_value=({'GLOAS_FORK_EPOCH': '1536', 'DEPOSIT_CHAIN_ID': '1'}, {})) as get:
        assert cl.get_gloas_fork_epoch() == 1536
    assert get.call_args.args[0] == 'eth/v1/config/spec'


@pytest.mark.unit
def test_get_gloas_fork_epoch_missing_on_pre_gloas_client_means_never():
    cl = _client()
    with patch.object(cl, '_get', return_value=({'DEPOSIT_CHAIN_ID': '1'}, {})):
        assert cl.get_gloas_fork_epoch() == FAR_FUTURE_EPOCH
