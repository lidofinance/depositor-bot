import logging
from typing import Any, Optional, Union

from eth_account import messages
from eth_account.signers.local import LocalAccount
from eth_typing import URI
from web3 import HTTPProvider, Web3
from web3._utils.request import make_post_request
from web3.types import RPCEndpoint, RPCResponse

logger = logging.getLogger(__name__)


class RelayProvider(HTTPProvider):
	def __init__(
		self,
		signature_account: LocalAccount,
		endpoint_uris: list[Union[URI, str]] = None,
		request_kwargs: Optional[Any] = None,
		session: Optional[Any] = None,
	):
		if not endpoint_uris:
			raise ValueError('endpoint_uris should not be empty')

		self.endpoint_uris = endpoint_uris

		super().__init__(endpoint_uris[0], request_kwargs, session)
		self.signature_account = signature_account

	def make_request(self, method: RPCEndpoint, params: Any, request_all: bool = False) -> RPCResponse:
		self.logger.debug('Making request HTTP. URI: %s, Method: %s', self.endpoint_uri, method)
		request_data = self.encode_rpc_request(method, params)

		message = messages.encode_defunct(text=Web3.keccak(text=request_data.decode('utf-8')).hex())
		signed_message = self.signature_account.sign_message(message)

		headers = self.get_request_headers() | {
			'X-Flashbots-Signature': f'{self.signature_account.address}:{signed_message.signature.hex()}'
		}

		if request_all:
			for endpoint_uri in self.endpoint_uris:
				raw_response = make_post_request(endpoint_uri, request_data, headers=headers)
		else:
			raw_response = make_post_request(self.endpoint_uri, request_data, headers=headers)

		response = self.decode_rpc_response(raw_response)
		self.logger.debug(
			'Getting response HTTP. URI: %s, ' 'Method: %s, Response: %s',
			self.endpoint_uri,
			method,
			response,
		)
		return response
