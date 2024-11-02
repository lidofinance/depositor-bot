import logging
from typing import Any
from urllib.parse import urlparse

from metrics.metrics import ETH_RPC_REQUESTS, ETH_RPC_REQUESTS_DURATION
from requests import HTTPError, Response
from web3.middleware.base import Web3Middleware
from web3.types import MakeRequestFn, RPCEndpoint, RPCResponse

logger = logging.getLogger(__name__)


class MetricsMiddleware(Web3Middleware):
    """
    Works correctly with MultiProvider and vanilla Providers.

    ETH_RPC_REQUESTS_DURATION - HISTOGRAM with requests time.
    ETH_RPC_REQUESTS - Counter with requests count, response codes and request domain.
    """

    def wrap_make_request(self, make_request: MakeRequestFn) -> MakeRequestFn:
        def middleware(method: RPCEndpoint, params: Any) -> RPCResponse:
            method, params = self.request_processor(method, params)

            try:
                with ETH_RPC_REQUESTS_DURATION.time():
                    response = self.response_processor(method, make_request(method, params))
            except HTTPError as ex:
                failed: Response = ex.response
                ETH_RPC_REQUESTS.labels(
                    method=method,
                    code=failed.status_code,
                    domain=urlparse(self._w3.provider.endpoint_uri).netloc,  # pyright: ignore
                ).inc()
                raise ex

            # https://www.jsonrpc.org/specification#error_object
            # https://eth.wiki/json-rpc/json-rpc-error-codes-improvement-proposal
            error = response.get('error')
            code: int = 0
            if isinstance(error, dict):
                code = error.get('code') or code

            ETH_RPC_REQUESTS.labels(
                method=method,
                code=code,
                domain=urlparse(self._w3.provider.endpoint_uri).netloc,  # pyright: ignore
            ).inc()

            return response

        return middleware
