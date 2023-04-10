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
    Network.Zhejiang: "0xDe82ADEd58dA35add75Ea4676239Ca169c8dCD15",
}

NODE_OPS_ADDRESSES = {
    Network.Mainnet: "0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5",
    Network.Görli: "0x9D4AF1Ee19Dad8857db3a45B0374c81c8A1C6320",
    Network.Zhejiang: "0xB099EC462e42Ac2570fB298B42083D7A499045D8",
}

DEPOSIT_CONTRACT = {
    Network.Mainnet: "0x00000000219ab540356cBB839Cbe05303d7705Fa",
    Network.Görli: "0xff50ed3d0ec03aC01D4C79aAd74928BFF48a7b2b",
    Network.Zhejiang: "0x4242424242424242424242424242424242424242",
}

DEPOSIT_SECURITY_MODULE = {
    Network.Mainnet: "0x710B3303fB508a84F10793c1106e32bE873C24cd",
    Network.Görli: "0xe57025E250275cA56f92d76660DEcfc490C7E79A",
    Network.Zhejiang: "0x57d31c50dB78e4d95C49Ab83EC011B4D0b0acF59",
}

STAKING_ROUTER = {
    Network.Görli: "0xa3Dbd317E53D363176359E10948BA0b1c0A4c820",
    Network.Mainnet: "0x0000000000000000000000000000000000000000",
    Network.Zhejiang: "0x0Ed4aCd69f6e00a2Ca0d141f8A900aC6BFaF70F0",
}

FLASHBOTS_RPC = {
    Network.Mainnet: "https://relay.flashbots.net",
    Network.Görli: "https://relay-goerli.flashbots.net",
}
