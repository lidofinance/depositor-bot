from typing import List, Optional, TypedDict, Union

from eth_account.signers.local import LocalAccount
from eth_typing import HexStr
from hexbytes import HexBytes
from web3.types import Hash32, TxParams


# unsigned transaction
class RelayBundleTx(TypedDict):
	transaction: TxParams
	signer: LocalAccount


# signed transaction
class RelayBundleRawTx(TypedDict):
	signed_transaction: HexBytes


# transaction dict taken from w3.eth.get_block('pending', full_transactions=True)
RelayBundleDictTx = TypedDict(
	'RelayBundleDictTx',
	{
		'accessList': list,
		'blockHash': HexBytes,
		'blockNumber': int,
		'chainId': str,
		'from': str,
		'gas': int,
		'gasPrice': int,
		'maxFeePerGas': int,
		'maxPriorityFeePerGas': int,
		'hash': HexBytes,
		'input': str,
		'nonce': int,
		'r': HexBytes,
		's': HexBytes,
		'to': str,
		'transactionIndex': int,
		'type': str,
		'v': int,
		'value': int,
	},
	total=False,
)


class RelayOpts(TypedDict):
	minTimestamp: Optional[int]
	maxTimestamp: Optional[int]
	revertingTxHashes: Optional[List[str]]
	replacementUuid: Optional[str]


# Type missing from eth_account, not really a part of flashbots web3 per sé
class SignTx(TypedDict, total=False):
	nonce: int
	chainId: int
	to: str
	data: str
	value: int
	gas: int
	gasPrice: int


# type alias
TxReceipt = Union[Hash32, HexBytes, HexStr]


# response from bundle or private tx submission
class SignedTxAndHash(TypedDict):
	signed_transaction: str
	hash: HexBytes
