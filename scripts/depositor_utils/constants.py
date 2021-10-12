from enum import IntEnum


class Network(IntEnum):
    Mainnet = 1
    Kovan = 42
    Rinkeby = 4
    Görli = 5
    xDai = 100
    Ropsten = 3


LIDO_CONTRACT_ADDRESSES = {
    Network.Mainnet: "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
    Network.Görli: "0x1643E812aE58766192Cf7D2Cf9567dF2C37e9B7F",
}

NODE_OPS_ADDRESSES = {
    Network.Mainnet: "0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5",
    Network.Görli: "0x9D4AF1Ee19Dad8857db3a45B0374c81c8A1C6320",
}

DEPOSIT_CONTRACT = {
    Network.Mainnet: "0x00000000219ab540356cBB839Cbe05303d7705Fa",
    Network.Görli: "0x07b39F4fDE4A38bACe212b546dAc87C58DfE3fDC",
}

DEPOSIT_SECURITY_MODULE = {
    Network.Mainnet: "0x00000000219ab540356cBB839Cbe05303d7705Fa",  # TODO: wrong mainnet address
    Network.Görli: "0x071954e987ee02BCAF4b29D6bD533A32E11607f3",
}

DEPOSIT_CONTRACT_DEPLOY_BLOCK = {
    Network.Mainnet: 11052984,
    Network.Görli: 3085928,
}

# 100 blocks is safe enough
UNREORGABLE_DISTANCE = 100
# reasonably high number (nb. if there is > 10000 deposit events infura will throw error)
EVENT_QUERY_STEP = 1000
