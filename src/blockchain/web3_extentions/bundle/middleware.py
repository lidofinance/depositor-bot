from typing import Any
from typing import Callable

from web3 import Web3
from web3.middleware import Middleware
from web3.types import RPCEndpoint, RPCResponse

from .provider import RelayProvider

RELAY_METHODS = [
    "eth_sendBundle",
    "eth_callBundle",
    "eth_cancelBundle",
]


def construct_relay_middleware(
    relay_provider: RelayProvider,
) -> Middleware:
    """
        Captures Relay RPC requests and sends them to the private relays
        while also injecting the required authorization headers

        Keyword arguments:
        flashbots_provider -- An HTTP provider instantiated with any authorization headers
        required
    """

    def relay_middleware(
        make_request: Callable[[RPCEndpoint, Any], Any], w3: Web3
    ) -> Callable[[RPCEndpoint, Any], RPCResponse]:
        def middleware(method: RPCEndpoint, params: Any) -> RPCResponse:
            if method not in RELAY_METHODS:
                return make_request(method, params)
            else:
                # otherwise intercept it and POST it to all provided relays
                return relay_provider.make_request(method, params, request_all=True)

        return middleware

    return relay_middleware
