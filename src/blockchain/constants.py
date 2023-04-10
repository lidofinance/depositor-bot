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
    Network.Görli: "0x5635C2Ac1bD6Fc2C7f9330C5D0B1279bAF41a271",
    Network.Zhejiang: "0xa8b936b61D17c1fC790d7ABeD6C6994d551A5F47",
}

NODE_OPS_ADDRESSES = {
    Network.Mainnet: "0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5",
    Network.Görli: "0x58Fd12AF2D496Bf517eE851eD94d1638DF1901e5",
    Network.Zhejiang: "0xd03809eFaED0F587471c5255ECE826EC0C9f7e99",
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
    Network.Görli: "0x200c147cd3F344Ad09bAeCadA0a945106df337B4",
    Network.Mainnet: "0x0000000000000000000000000000000000000000",
    Network.Zhejiang: "0xFA4Ae98c57224EDFEc2F07f29E75A301D09869f1",
}

FLASHBOTS_RPC = {
    Network.Mainnet: "https://relay.flashbots.net",
    Network.Görli: "https://relay-goerli.flashbots.net",
}
