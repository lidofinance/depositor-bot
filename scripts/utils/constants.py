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
    Network.Görli: "0xff50ed3d0ec03ac01d4c79aad74928bff48a7b2b",
}

DEPOSIT_SECURITY_MODULE = {
    Network.Mainnet: "0xDb149235B6F40dC08810AA69869783Be101790e7",
    Network.Görli: "0xed23ad3ea5fb9d10e7371caef1b141ad1c23a80c",
}

FLASHBOTS_RPC = {
    Network.Mainnet: "https://rpc.flashbots.net",
    Network.Görli: "https://relay-goerli.flashbots.net",
}

DEPOSIT_CONTRACT_DEPLOY_BLOCK = {
    Network.Mainnet: 11052984,
    Network.Görli: 3085928,
}

# 100 blocks is safe enough
UNREORGABLE_DISTANCE = 100
# reasonably high number (nb. if there is > 10000 deposit events infura will throw error)
EVENT_QUERY_STEP = 1000
