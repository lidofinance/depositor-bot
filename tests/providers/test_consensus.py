# pylint: disable=protected-access
"""Simple tests for the consensus client responses validity."""

from unittest.mock import Mock

import pytest
import requests
import variables
from providers.consensus import ConsensusClient


@pytest.fixture
def consensus_client(request):
    params = getattr(request, 'param', {})
    hosts = params.get('hosts', variables.CL_API_URLS)
    if not hosts:
        pytest.skip('CL_API_URLS is not configured.')

    return ConsensusClient(
        hosts=hosts,
        request_timeout=30,
        retry_total=3,
        retry_backoff_factor=1,
    )


@pytest.mark.integration
def test_get_block_details(consensus_client: ConsensusClient):
    block_details = consensus_client.get_block_details('head')

    assert block_details
    assert int(block_details['slot']) >= 0
    assert int(block_details['proposer_index']) >= 0


@pytest.mark.integration
def test_get_block_header(consensus_client: ConsensusClient):
    block_header = consensus_client.get_block_header('head')

    assert block_header
    assert int(block_header['slot']) >= 0
    assert int(block_header['proposer_index']) >= 0
    assert len(block_header['parent_root']) == 66
    assert len(block_header['state_root']) == 66
    assert len(block_header['body_root']) == 66


@pytest.mark.integration
def test_get_beacon_state_ssz(consensus_client: ConsensusClient):
    block_header = consensus_client.get_block_header('head')
    state_root = block_header['state_root']

    state_ssz = consensus_client.get_beacon_state_ssz(state_root)

    assert state_ssz
    assert isinstance(state_ssz, bytes)


@pytest.mark.integration
def test_get_chain_id_with_provider(consensus_client: ConsensusClient):
    chain_id = consensus_client._get_chain_id_with_provider(0)

    assert chain_id > 0


@pytest.mark.unit
def test_get_returns_not_dict(consensus_client: ConsensusClient):
    resp = requests.Response()
    resp.status_code = 200
    resp._content = b'{"data": 1}'

    consensus_client.session.get = Mock(return_value=resp)

    with pytest.raises(ValueError, match='Expected mapping response'):
        consensus_client.get_block_details('head')

    with pytest.raises(ValueError, match='Expected mapping response'):
        consensus_client.get_block_header('head')

    with pytest.raises(ValueError, match='Expected mapping response'):
        consensus_client._get_chain_id_with_provider(0)
