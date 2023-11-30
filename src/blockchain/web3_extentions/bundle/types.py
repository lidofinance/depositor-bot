from typing import TypedDict, List, Union, Optional

from eth_account.signers.local import LocalAccount
from eth_typing import HexStr
from hexbytes import HexBytes
from web3.types import TxParams, Hash32

# unsigned transaction
RelayBundleTx = TypedDict(
    "RelayBundleTx",
    {
        "transaction": TxParams,
        "signer": LocalAccount,
    },
)

# signed transaction
RelayBundleRawTx = TypedDict(
    "RelayBundleRawTx",
    {
        "signed_transaction": HexBytes,
    },
)

# transaction dict taken from w3.eth.get_block('pending', full_transactions=True)
RelayBundleDictTx = TypedDict(
    "RelayBundleDictTx",
    {
        "accessList": list,
        "blockHash": HexBytes,
        "blockNumber": int,
        "chainId": str,
        "from": str,
        "gas": int,
        "gasPrice": int,
        "maxFeePerGas": int,
        "maxPriorityFeePerGas": int,
        "hash": HexBytes,
        "input": str,
        "nonce": int,
        "r": HexBytes,
        "s": HexBytes,
        "to": str,
        "transactionIndex": int,
        "type": str,
        "v": int,
        "value": int,
    },
    total=False,
)

RelayOpts = TypedDict(
    "RelayOpts",
    {
        "minTimestamp": Optional[int],
        "maxTimestamp": Optional[int],
        "revertingTxHashes": Optional[List[str]],
        "replacementUuid": Optional[str],
    },
)


# Type missing from eth_account, not really a part of flashbots web3 per sé
SignTx = TypedDict(
    "SignTx",
    {
        "nonce": int,
        "chainId": int,
        "to": str,
        "data": str,
        "value": int,
        "gas": int,
        "gasPrice": int,
    },
    total=False,
)

# type alias
TxReceipt = Union[Hash32, HexBytes, HexStr]

# response from bundle or private tx submission
SignedTxAndHash = TypedDict(
    "SignedTxAndHash",
    {
        "signed_transaction": str,
        "hash": HexBytes,
    },
)
