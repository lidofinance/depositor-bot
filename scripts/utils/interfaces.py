from brownie import interface

from scripts.utils.constants import (
    STMATIC_CONTRACT_ADDRESSES,
    NODE_OPERATOR_REGISTRY_CONTRACT_ADDRESSES,
    ERC20_CONTRACT_ADDRESSES,
)
from scripts.utils.variables import WEB3_CHAIN_ID, ACCOUNT

StMATICInterface = interface.StMATIC(STMATIC_CONTRACT_ADDRESSES[WEB3_CHAIN_ID], owner=ACCOUNT)
NodeOperatorRegistryInterface = interface.NodeOperatorRegistry(NODE_OPERATOR_REGISTRY_CONTRACT_ADDRESSES[WEB3_CHAIN_ID], owner=ACCOUNT)
ERC20Interface = interface.ERC20(ERC20_CONTRACT_ADDRESSES[WEB3_CHAIN_ID], owner=ACCOUNT)

def get_interface(add):
    return interface.ValidatorShare(add, owner=ACCOUNT)
