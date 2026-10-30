from typing import Any

import requests
from providers.consistency import ProviderConsistencyModule
from web3 import Web3
from web3.providers.rpc.utils import ExceptionRetryConfiguration
from web3.types import RPCEndpoint
from web3_multi_provider import FallbackProvider

# web3 retries a failed request on the same endpoint before the fallback moves on, each attempt bounded
# by its 30 s DEFAULT_HTTP_TIMEOUT. Its default of 5 attempts holds every call on a hung endpoint for
# ~150 s; 2 keep it at ~60 s, well inside the executor's shortest deadline (the 384 s block wait), so
# the next endpoint is reached before the watchdog ends the process. `errors` must be explicit: the
# class defaults it to None, which fails on the first retry.
EL_EXCEPTION_RETRY_CONFIGURATION = ExceptionRetryConfiguration(
    errors=(ConnectionError, requests.HTTPError, requests.Timeout),
    retries=2,
)


class FallbackProviderModule(ProviderConsistencyModule, FallbackProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_all_providers(self) -> list[Any]:
        return self._providers  # type: ignore[attr-defined]

    def _get_chain_id_with_provider(self, provider_index: int) -> int:
        response_chain_id = self._providers[provider_index].make_request(RPCEndpoint('eth_chainId'), [])  # type: ignore[attr-defined]
        return Web3.to_int(hexstr=response_chain_id.get('result'))
