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


FLASHBOTS_RPC = {
    Network.Mainnet: "https://relay.flashbots.net",
    Network.Görli: "https://relay-goerli.flashbots.net",
}


LIDO_LOCATOR = {
    Network.Mainnet: '0xC1d0b3DE6792Bf6b4b37EccdcC24e45978Cfd2Eb',
    Network.Görli: '0x1eDf09b5023DC86737b59dE68a8130De878984f5',
}


DEPOSIT_CONTRACT = {
    Network.Mainnet: "0x00000000219ab540356cBB839Cbe05303d7705Fa",
    Network.Görli: "0xff50ed3d0ec03aC01D4C79aAd74928BFF48a7b2b",
}

SLOT_TIME = 12
