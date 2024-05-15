from typing import Union

from eth_account.signers.local import LocalAccount
from eth_typing import URI
from web3 import Web3
from web3._utils.module import attach_modules

from .middleware import construct_relay_middleware
from .provider import RelayProvider
from .relay import Relay


def activate_relay(
	w3: Web3,
	signature_account: LocalAccount,
	endpoint_uris: list[Union[URI, str]] = None,
):
	"""
	Injects the flashbots module and middleware to w3.
	"""

	relay_provider = RelayProvider(signature_account, endpoint_uris)

	relay_middleware = construct_relay_middleware(relay_provider)
	w3.middleware_onion.add(relay_middleware)

	# attach modules to add the new namespace commands
	attach_modules(w3, {'relay': (Relay,)})
