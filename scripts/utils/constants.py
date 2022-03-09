from enum import IntEnum

class Network(IntEnum):
    Mainnet = 1
    Görli = 5


STMATIC_CONTRACT_ADDRESSES = {
    Network.Mainnet: "0x9ee91F9f426fA633d227f7a9b000E28b9dfd8599",
    Network.Görli: "0x9A7c69A167160C507602ecB3Df4911e8E98e1279",
}

NODE_OPERATOR_REGISTRY_CONTRACT_ADDRESSES = {
    Network.Mainnet: "0x797C1369e578172112526dfcD0D5f9182067c928",
    Network.Görli: "0xb1f3f45360Cf0A30793e38C18dfefCD0d5136f9a",
}

ERC20_CONTRACT_ADDRESSES = {
    Network.Mainnet: "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0",
    Network.Görli: "0x499d11E0b6eAC7c0593d8Fb292DCBbF815Fb29Ae",
}
