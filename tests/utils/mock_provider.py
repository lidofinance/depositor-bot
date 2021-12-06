import os
from typing import Any

from web3 import HTTPProvider
from web3._utils.request import make_post_request
from web3.providers import JSONBaseProvider
from web3.types import RPCEndpoint, RPCResponse


class MockProvider(JSONBaseProvider):
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

        infura_project_id = os.getenv('WEB3_INFURA_PROJECT_ID')
        network = os.getenv('NETWORK')
        prov = HTTPProvider(f'https://{network}.infura.io/v3/{infura_project_id}')
        request_data = prov.encode_rpc_request(method, params)
        raw_response = make_post_request(
            prov.endpoint_uri,
            request_data,
            **prov.get_request_kwargs()
        )
        response = prov.decode_rpc_response(raw_response)

        # print(method)
        # print(f'({params}, {response}),')

        return response
