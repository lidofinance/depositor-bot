import logging
from typing import Callable, TypedDict

from blockchain.typings import Web3
from cryptography.verify_signature import verify_message_with_signature
from eth_typing import Hash32
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from schema import And, Schema
from transport.msg_types.base import ADDRESS_REGREX, HASH_REGREX, HEX_BYTES_REGREX, Signature, SignatureSchema
from utils.bytes import from_hex_string_to_bytes

logger = logging.getLogger(__name__)


UnvetMessageSchema = Schema(
	{
		'type': And(str, lambda t: t in ('unvet',)),
		'blockNumber': int,
		'blockHash': And(str, HASH_REGREX.validate),
		'guardianAddress': And(str, ADDRESS_REGREX.validate),
		'signature': SignatureSchema,
		'stakingModuleId': int,
		'operatorIds': And(str, HEX_BYTES_REGREX.validate),
		'vettedKeysByOperator': And(str, HEX_BYTES_REGREX.validate),
	},
	ignore_extra_keys=True,
)


class UnvetMessage(TypedDict):
	type: str
	blockNumber: int
	blockHash: Hash32
	guardianAddress: str
	signature: Signature
	stakingModuleId: int
	nonce: int
	operatorIds: str
	vettedKeysByOperator: str


def get_unvet_messages_sign_filter(web3: Web3) -> Callable:
	def check_unvet_message(msg: UnvetMessage) -> bool:
		unvet_prefix = web3.lido.deposit_security_module.get_unvet_message_prefix()

		verified = verify_message_with_signature(
			data=[
				unvet_prefix,
				msg['blockNumber'],
				msg['blockHash'],
				msg['stakingModuleId'],
				msg['nonce'],
				from_hex_string_to_bytes(msg['operatorIds']),
				from_hex_string_to_bytes(msg['vettedKeysByOperator']),
			],
			abi=['bytes32', 'uint256', 'bytes32', 'uint256', 'uint256', 'bytes', 'bytes'],
			address=msg['guardianAddress'],
			vrs=(
				msg['signature']['v'],
				msg['signature']['r'],
				msg['signature']['s'],
			),
		)

		if not verified:
			logger.error({'msg': 'Message verification failed.', 'value': msg})
			UNEXPECTED_EXCEPTIONS.labels('get_unvet_messages_sign_filter').inc()

		return verified

	return check_unvet_message
