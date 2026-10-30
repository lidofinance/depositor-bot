from unittest.mock import Mock, patch

import pytest
from web3.types import RPCEndpoint
from web3_multi_provider import NoActiveProviderError

from providers.fallback_provider import PROVIDER_COOLDOWN_SECONDS, CooldownFallbackProvider

OK = {'jsonrpc': '2.0', 'id': 1, 'result': '0x1'}


def _provider(*responses) -> CooldownFallbackProvider:
    """One endpoint per entry: an exception makes every call to it fail, anything else is returned."""
    provider = CooldownFallbackProvider([f'http://rpc-{i}.example' for i in range(len(responses))])
    for endpoint, response in zip(provider._providers, responses, strict=True):
        endpoint.make_request = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
    return provider


def _request(provider: CooldownFallbackProvider):
    return provider.make_request(RPCEndpoint('eth_blockNumber'), [])


def _calls(provider: CooldownFallbackProvider) -> list[int]:
    return [endpoint.make_request.call_count for endpoint in provider._providers]


@pytest.mark.unit
def test_healthy_primary_serves_every_request():
    provider = _provider(OK, OK)

    _request(provider)
    _request(provider)

    assert _calls(provider) == [2, 0]


@pytest.mark.unit
def test_failed_primary_is_skipped_while_cooling():
    provider = _provider(Exception('429 Too Many Requests'), OK)

    for _ in range(3):
        assert _request(provider) == OK

    assert _calls(provider) == [1, 3]


@pytest.mark.unit
def test_primary_is_preferred_again_after_cooldown():
    provider = _provider(Exception('429 Too Many Requests'), OK)

    with patch('providers.fallback_provider.time.monotonic', return_value=1000.0):
        _request(provider)
    provider._providers[0].make_request = Mock(return_value=OK)
    with patch('providers.fallback_provider.time.monotonic', return_value=1000.0 + PROVIDER_COOLDOWN_SECONDS):
        _request(provider)

    assert provider._providers[0].make_request.call_count == 1
    assert provider._providers[1].make_request.call_count == 1


@pytest.mark.unit
def test_cooling_endpoints_are_still_tried_last():
    provider = _provider(Exception('429 Too Many Requests'), OK, OK)
    _request(provider)
    provider._providers[1].make_request = Mock(side_effect=Exception('down'))
    provider._providers[2].make_request = Mock(side_effect=Exception('down'))
    provider._providers[0].make_request = Mock(return_value=OK)

    assert _request(provider) == OK
    assert _calls(provider) == [1, 1, 1]


@pytest.mark.unit
def test_all_endpoints_failing_still_raises():
    provider = _provider(Exception('down'), Exception('down'))

    for _ in range(2):
        with pytest.raises(NoActiveProviderError):
            _request(provider)

    assert _calls(provider) == [2, 2]


@pytest.mark.unit
def test_cooldown_is_logged_once_per_window(caplog):
    provider = _provider(Exception('down'), Exception('down'))

    for _ in range(2):
        with pytest.raises(NoActiveProviderError):
            _request(provider)

    cooldown_logs = [r for r in caplog.records if r.name == 'providers.fallback_provider']
    assert len(cooldown_logs) == 2
