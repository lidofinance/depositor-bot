import logging
from typing import Callable, TypedDict

from blockchain.typings import Web3
from cryptography.verify_signature import verify_message_with_signature
from metrics.metrics import UNEXPECTED_EXCEPTIONS
from schema import And, Schema
from transport.msg_types.base import ADDRESS_REGREX, Signature, SignatureSchema

logger = logging.getLogger(__name__)


"""
Pause msg example:
{
    "blockHash": "0xe41c0212516a899c455203e833903c802338daa3048bc637b623f6fba0a1685c",
    "blockNumber": 5669490,
    "guardianAddress": "0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A",
    "guardianIndex": 0,
    "signature": {
        "_vs": "0xd4933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
        "r": "0xbaa668505cd496caaf7117dd074338197200175057909ab73a04463656bdb0fa",
        "recoveryParam": 1,
        "s": "0x54933925f5f97a9632b4b1bc621a1c2771d58eaf6eee27dcf915eac8af010537",
        "v": 28
    },
    "type": "pause"
}
"""
PauseMessageSchema = Schema(
	{
		'type': And(str, lambda t: t in ('pause',)),
		'blockNumber': int,
		'guardianAddress': And(str, ADDRESS_REGREX.validate),
		'signature': SignatureSchema,
		# 'stakingModuleId': int
	},
	ignore_extra_keys=True,
)


class PauseMessage(TypedDict):
	type: str
	blockNumber: int
	guardianAddress: str
	signature: Signature
	stakingModuleId: int


def get_pause_messages_sign_filter(web3: Web3) -> Callable:
	def check_pause_message(msg: PauseMessage) -> bool:
		pause_prefix = web3.lido.deposit_security_module.get_pause_message_prefix()

		if msg.get('stakingModuleId', -1) != -1:
			verified = verify_message_with_signature(
				data=[pause_prefix, msg['blockNumber'], msg['stakingModuleId']],
				abi=['bytes32', 'uint256', 'uint256'],
				address=msg['guardianAddress'],
				vrs=(
					msg['signature']['v'],
					msg['signature']['r'],
					msg['signature']['s'],
				),
			)
		else:
			verified = verify_message_with_signature(
				data=[pause_prefix, msg['blockNumber']],
				abi=['bytes32', 'uint256'],
				address=msg['guardianAddress'],
				vrs=(
					msg['signature']['v'],
					msg['signature']['r'],
					msg['signature']['s'],
				),
			)

		if not verified:
			logger.error({'msg': 'Message verification failed.', 'value': msg})
			UNEXPECTED_EXCEPTIONS.labels('pause_message_verification_failed').inc()

		return verified

	return check_pause_message
