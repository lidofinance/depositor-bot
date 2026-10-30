import logging
import time
from collections.abc import Iterator
from typing import Any

from web3 import HTTPProvider, Web3
from web3.types import RPCEndpoint
from web3_multi_provider import FallbackProvider

from providers.consistency import ProviderConsistencyModule

logger = logging.getLogger(__name__)

# Each failed request to an endpoint costs web3's in-provider retries (~2s) before failover. A failing
# endpoint is moved to the back of the order for this long, so a rate-limited primary costs that once
# per window instead of on every request, and is preferred again as soon as the window ends.
PROVIDER_COOLDOWN_SECONDS = 60


class CooldownFallbackProvider(FallbackProvider):
    """Fallback in configured order, skipping endpoints that failed recently.

    Cooling endpoints are still tried, after the healthy ones, so a request never has fewer
    endpoints to go through than plain `FallbackProvider` would give it.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cooldown_until: dict[int, float] = {}

    def get_providers(self) -> Iterator[HTTPProvider]:
        now = time.monotonic()
        indexes = range(len(self._providers))
        healthy = [i for i in indexes if self._cooldown_until.get(i, 0) <= now]
        cooling = [i for i in indexes if i not in healthy]

        for index in healthy + cooling:
            yield self._providers[index]
            # The failover loop only asks for the next endpoint when this one raised.
            self._put_on_cooldown(index)

    def _put_on_cooldown(self, index: int) -> None:
        now = time.monotonic()
        if self._cooldown_until.get(index, 0) <= now:
            logger.warning({'msg': 'Provider put on cooldown.', 'index': index, 'seconds': PROVIDER_COOLDOWN_SECONDS})
        self._cooldown_until[index] = now + PROVIDER_COOLDOWN_SECONDS


class FallbackProviderModule(ProviderConsistencyModule, CooldownFallbackProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_all_providers(self) -> list[Any]:
        return self._providers  # type: ignore[attr-defined]

    def _get_chain_id_with_provider(self, provider_index: int) -> int:
        response_chain_id = self._providers[provider_index].make_request(RPCEndpoint('eth_chainId'), [])  # type: ignore[attr-defined]
        return Web3.to_int(hexstr=response_chain_id.get('result'))
