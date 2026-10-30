import pytest
from web3._utils.http import DEFAULT_HTTP_TIMEOUT

from blockchain.constants import SLOT_TIME
from providers.fallback_provider import EL_EXCEPTION_RETRY_CONFIGURATION, FallbackProviderModule


@pytest.mark.unit
def test_hung_endpoint_is_given_up_before_the_shortest_cycle_deadline():
    config = EL_EXCEPTION_RETRY_CONFIGURATION
    backoff = sum(config.backoff_factor * 2**i for i in range(config.retries - 1))
    # Executor._wait_until_next_block with blocks_between_execution=1 — the pauser's block wait.
    assert config.retries * DEFAULT_HTTP_TIMEOUT + backoff < 32 * SLOT_TIME


@pytest.mark.unit
@pytest.mark.filterwarnings('ignore:prometheus_client is installed but init_metrics')
def test_hung_endpoint_fails_over_after_the_configured_attempts(hung_host, healthy_host):
    """Over real sockets: each attempt on the hung endpoint times out, and after `retries` of them the
    fallback answers. Also proves `errors` is usable — left as None, the first retry raises TypeError."""
    hung_url, accepted = hung_host
    healthy_url, hits = healthy_host
    provider = FallbackProviderModule(
        [hung_url, healthy_url],
        # Shorter than web3's 30 s so the test is quick; the attempt count is what is under test.
        request_kwargs={'timeout': 0.2},
        exception_retry_configuration=EL_EXCEPTION_RETRY_CONFIGURATION,
    )

    assert provider.make_request('eth_blockNumber', [])['result'] == '0x1'
    assert len(accepted) == EL_EXCEPTION_RETRY_CONFIGURATION.retries
    assert hits
