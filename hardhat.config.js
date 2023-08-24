/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.19",
  networks: {
    hardhat: {
      mining: {
        auto: true,
        interval: 12000
      }
    }
  },
  localhost: {
    timeout: 100_000
  },
};
