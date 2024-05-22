from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.transaction import TransactionUtils
from web3 import Web3 as _Web3


class Web3(_Web3):
    lido: LidoContracts
    transaction: TransactionUtils
