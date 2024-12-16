import logging
from typing import Any, Callable, Set, cast
from urllib.parse import urlparse

from metrics.metrics import ETH_RPC_REQUESTS, ETH_RPC_REQUESTS_DURATION, ONCHAIN_TRANSPORT_ETH_RPC_REQUESTS
from requests import HTTPError, Response
from web3 import Web3
from web3.middleware import construct_simple_cache_middleware
from web3.types import RPCEndpoint, RPCResponse

logger = logging.getLogger(__name__)


def add_requests_metric_middleware(web3: Web3) -> Web3:
    """
    Works correctly with MultiProvider and vanilla Providers.

    ETH_RPC_REQUESTS_DURATION - HISTOGRAM with requests time.
    ETH_RPC_REQUESTS - Counter with requests count, response codes and request domain.
    """

    def metrics_collector(make_request: Callable[[RPCEndpoint, Any], RPCResponse], w3: Web3) -> Callable[[RPCEndpoint, Any], RPCResponse]:
        """Constructs a middleware which measure requests parameters"""
        chain_id = w3.eth.chain_id
        metrics = ETH_RPC_REQUESTS
        if chain_id != 1:
            metrics = ONCHAIN_TRANSPORT_ETH_RPC_REQUESTS

        def middleware(method: RPCEndpoint, params: Any) -> RPCResponse:
            labeled_metric = metrics.labels(
                method=method,
                domain=urlparse(web3.provider.endpoint_uri).netloc,  # pyright: ignore
            )
            try:
                with ETH_RPC_REQUESTS_DURATION.time():
                    response = make_request(method, params)
            except HTTPError as ex:
                failed: Response = ex.response
                labeled_metric.labels(code=failed.status_code).inc()
                raise

            # https://www.jsonrpc.org/specification#error_object
            # https://eth.wiki/json-rpc/json-rpc-error-codes-improvement-proposal
            error = response.get('error')
            code: int = 0
            if isinstance(error, dict):
                code = error.get('code') or code

            labeled_metric.labels(code=code).inc()
            return response

        return middleware

    web3.middleware_onion.inject(metrics_collector, layer=0)
    return web3


def add_cache_middleware(web3: Web3) -> Web3:
    web3.middleware_onion.inject(
        construct_simple_cache_middleware(
            rpc_whitelist=cast(
                Set[RPCEndpoint],
                {
                    'eth_chainId',
                },
            )
        ),
        layer=0,
    )
    return web3


def add_middlewares(web3: Web3) -> Web3:
    """
    Cache middleware should go first to avoid rewriting metrics for cached requests.
    If middleware has level = 0, the middleware will be appended to the end of the middleware list.
    So we need [..., cache, other middlewares]
    """
    add_cache_middleware(web3)
    add_requests_metric_middleware(web3)
    return web3
