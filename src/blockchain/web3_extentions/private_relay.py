# pyright: reportTypedDictNotRequiredAccess=false

"""
Client for interacting with the mev-share JSON-RPC API
"""

import json

import requests
from eth_account import Account
from eth_account.datastructures import SignedTransaction
from eth_account.messages import encode_defunct
from eth_typing import URI
from web3 import Web3


class PrivateRelayException(Exception):
    pass


class PrivateRelayClient:
    """
    Sends private transaction to private builders through flashbots rpc.
    """

    def __init__(
        self,
        w3: Web3,
        rpc_url: URI,
        sign_account: str,
    ):
        self.w3 = w3
        self.rpc_url = rpc_url
        self.account = Account.from_key(sign_account)

    def send_private_tx(self, tx: SignedTransaction, timeout_in_blocks: int):
        req_params = self._build_mev_send_bundle_params(tx, timeout_in_blocks)

        try:
            response = self._handle_post_request('eth_sendPrivateTransaction', req_params)
        except Exception as error:
            raise PrivateRelayException(*error.args) from error

        if 'result' not in response:
            raise PrivateRelayException(response.get('error', response))

        return response['result']

    def _handle_post_request(
        self,
        method: str,
        params: list[dict],
    ):
        headers, signature, body = self._get_rpc_request(method, params, self.account)

        return requests.post(
            url=self.rpc_url,
            data=json.dumps(body),
            headers=headers,
            timeout=15,
        ).json()

    @staticmethod
    def _get_rpc_request(method: str, params: list[dict], signer: Account):
        body = {
            'jsonrpc': '2.0',
            'id': '1',
            'method': method,
            'params': params,
        }
        message = encode_defunct(text=Web3.keccak(text=json.dumps(body)).hex())
        signature = signer.address + ':' + signer.sign_message(message).signature.hex()  # pyright: ignore
        headers = {
            'Content-Type': 'application/json',
            'X-Flashbots-Signature': signature,
        }
        return headers, signature, body

    def _build_mev_send_bundle_params(self, tx: SignedTransaction, timeout_in_blocks: int) -> list[dict]:
        """
        https://docs.flashbots.net/flashbots-auction/advanced/rpc-endpoint#mev_sendbundle
        """
        return [
            {
                'tx': tx.rawTransaction.hex(),
                'maxBlockNumber': hex(self.w3.eth.get_block('pending')['number'] + timeout_in_blocks),
                'preferences': {
                    'builders': [
                        'rpc.flashbots.net',
                        'https://rpc.f1b.io',
                        'rsync-builder.xyz',
                        'rpc.beaverbuild.org',
                        'builder0x69.io',
                        'rpc.titanbuilder.xyz',
                        'builder.eigenphi.io',
                        'builder.eigenphi.io',
                        'https://builder.gmbit.co/rpc',
                        'rpc.payload.de',
                        'rpc.lokibuilder.xyz',
                        'https://buildai.net',
                        'rpc.mevshare.jetbldr.xyz',
                        'flashbots.rpc.tbuilder.xyz',
                        'rpc.penguinbuild.org',
                        'rpc.bobthebuilder.xyz',
                    ]
                },
            }
        ]
