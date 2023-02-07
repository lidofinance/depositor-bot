from typing import Any

from web3.providers import JSONBaseProvider
from web3.types import RPCEndpoint, RPCResponse


class MockProvider(JSONBaseProvider):
    _current_provider_index = 0

    def __init__(self, mock_object: dict):
        self._mock_object = mock_object
        super().__init__()

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        if method in self._mock_object:
            result = next((x for x in self._mock_object[method] if x[0] == params), None)
            if result is not None:
                return result[1]

            result = next((x for x in self._mock_object[method] if x[0] == 'default'), None)
            if result is not None:
                return result[1]

        raise Exception('There is no mock for response')
