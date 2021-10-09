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
    Network.Ropsten: "0xd40EefCFaB888C9159a61221def03bF77773FC19",
    Network.Rinkeby: "0xF4242f9d78DB7218Ad72Ee3aE14469DBDE8731eD",
}

NODE_OPS_ADDRESSES = {
    Network.Mainnet: "0x55032650b14df07b85bF18A3a3eC8E0Af2e028d5",
    Network.Görli: "0x9D4AF1Ee19Dad8857db3a45B0374c81c8A1C6320",
    Network.Ropsten: "0x32c6f34F3920E8c0074241619c02be2fB722a68d",
    Network.Rinkeby: "0x776dFe7Ec5D74526Aa65898B7d77FCfdf15ffBe6",
}

DEPOSIT_CONTRACT = {
    Network.Mainnet: "0x00000000219ab540356cBB839Cbe05303d7705Fa",
    Network.Görli: "0x07b39F4fDE4A38bACe212b546dAc87C58DfE3fDC",
}
