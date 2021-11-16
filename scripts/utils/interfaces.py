from brownie import interface

from scripts.utils.constants import (
    LIDO_CONTRACT_ADDRESSES,
    NODE_OPS_ADDRESSES,
    DEPOSIT_SECURITY_MODULE,
    DEPOSIT_CONTRACT,
)
from scripts.utils.variables import WEB3_CHAIN_ID, ACCOUNT


LidoInterface = interface.Lido(LIDO_CONTRACT_ADDRESSES[WEB3_CHAIN_ID], owner=ACCOUNT)

NodeOperatorsRegistryInterface = interface.NodeOperatorRegistry(NODE_OPS_ADDRESSES[WEB3_CHAIN_ID], owner=ACCOUNT)

DepositSecurityModuleInterface = interface.DepositSecurityModule(DEPOSIT_SECURITY_MODULE[WEB3_CHAIN_ID], owner=ACCOUNT)

DepositContractInterface = interface.DepositContract(DEPOSIT_CONTRACT[WEB3_CHAIN_ID], owner=ACCOUNT)
