from enum import IntEnum


class Network(IntEnum):
    Mainnet = 1
    Kovan = 42
    Rinkeby = 4
    Görli = 5
    xDai = 100
    Ropsten = 3
    Zhejiang = 1337803


NETWORK_CHAIN_ID = {
    'mainnet': 1,
    'goerli': 5,
    'zhejiang': 1337803,
}


LIDO_CONTRACT_ADDRESSES = {
    Network.Mainnet: "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
    Network.Görli: "0x1643E812aE58766192Cf7D2Cf9567dF2C37e9B7F",
    Network.Zhejiang: "0xEC9ac956D7C7fE5a94919fD23BAc4a42f950A403",
}

NODE_OPS_ADDRESSES = {
    Network.Mainnet: "0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5",
    Network.Görli: "0x9D4AF1Ee19Dad8857db3a45B0374c81c8A1C6320",
    Network.Zhejiang: "0x8a1E2986E52b441058325c315f83C9D4129bDF72",
}

DEPOSIT_CONTRACT = {
    Network.Mainnet: "0x00000000219ab540356cBB839Cbe05303d7705Fa",
    Network.Görli: "0xff50ed3d0ec03aC01D4C79aAd74928BFF48a7b2b",
    Network.Zhejiang: "0x4242424242424242424242424242424242424242",
}

DEPOSIT_SECURITY_MODULE = {
    Network.Mainnet: "0x710B3303fB508a84F10793c1106e32bE873C24cd",
    Network.Görli: "0x7DC1C1ff64078f73C98338e2f17D1996ffBb2eDe",
    Network.Zhejiang: "0x48bEdD13FF63F7Cd4d349233B6a57Bff285f8E32",
}

FLASHBOTS_RPC = {
    Network.Mainnet: "https://relay.flashbots.net",
    Network.Görli: "https://relay-goerli.flashbots.net",
    Network.Zhejiang: "",
}
