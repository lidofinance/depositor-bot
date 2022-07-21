import logging
from typing import Any, Callable

from requests import Response, HTTPError
from web3 import Web3
from web3.types import RPCEndpoint, RPCResponse

from scripts.utils.metrics import ETH_RPC_REQUESTS_DURATION, ETH_RPC_REQUESTS

logger = logging.getLogger(__name__)


def metrics_collector(
    make_request: Callable[[RPCEndpoint, Any], RPCResponse], w3: Web3
) -> Callable[[RPCEndpoint, Any], RPCResponse]:
    """Constructs a middleware which measure requests parameters"""

    def middleware(method: RPCEndpoint, params: Any) -> RPCResponse:

        try:
            with ETH_RPC_REQUESTS_DURATION.time():
                response = make_request(method, params)
        except HTTPError as ex:
            failed: Response = ex.response
            ETH_RPC_REQUESTS.labels(
                method=method,
                code=failed.status_code,
            ).inc()
            raise
        else:
            # https://www.jsonrpc.org/specification#error_object
            # https://eth.wiki/json-rpc/json-rpc-error-codes-improvement-proposal
            error = response.get("error")
            code: int = 0
            if isinstance(error, dict):
                code = error.get("code") or code
            ETH_RPC_REQUESTS.labels(
                method=method,
                code=code,
            ).inc()

            return response

    return middleware
