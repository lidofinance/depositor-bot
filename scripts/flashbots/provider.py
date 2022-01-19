import logging
from typing import Any, Union, Optional

from eth_account.signers.local import LocalAccount
from eth_typing import URI
from web3 import HTTPProvider
from web3._utils.request import make_post_request
from web3.types import RPCEndpoint, RPCResponse
from web3 import Web3
from eth_account import Account, messages


class FlashbotProvider(HTTPProvider):
    logger = logging.getLogger("web3.providers.FlashbotProvider")

    def __init__(
            self,
            signature_account: LocalAccount,
            endpoint_uri: Optional[Union[URI, str]] = None,
            request_kwargs: Optional[Any] = None,
            session: Optional[Any] = None,
    ):
        super().__init__(endpoint_uri, request_kwargs, session)
        self.signature_account = signature_account

    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        request_data = self.encode_rpc_request(method, params)

        message = messages.encode_defunct(
            text=Web3.keccak(text=request_data.decode("utf-8")).hex()
        )
        signed_message = Account.sign_message(
            message, private_key=self.signature_account.privateKey.hex()
        )

        headers = {
            **self.get_request_headers(),
            "X-Flashbots-Signature": f"{self.signature_account.address}:{signed_message.signature.hex()}"
        }

        raw_response = make_post_request(
            self.endpoint_uri, request_data, headers=headers
        )
        return self.decode_rpc_response(raw_response)
