# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Lido Depositor bot

## Depositor bot description
Depositor bot - Deposits buffered ether via depositBufferedEther call on "DepositSecurityModule" smart contract using special gas strategy.

The strategy is to check two things: how much buffered ether on smart contract are and gas fee.

We deposit when all the following points are correct:
- We received council signatures enough for quorum.
- Gas fee is lower or equal than 5-th percentile for past day.
- There are buffered ether more or equal than calculation from special formula that depend on gas fee.

## Pauser bot
If one of the councils send pause message (means something very bad going on), depositor bot try to send tx that will pause protocol.  
Also, council daemon also tries to pause protocol by itself


## How to install

Only for development: [Ganache CLI](https://github.com/trufflesuite/ganache-cli) is required to run [Brownie](https://github.com/eth-brownie/brownie)

```bash 
npm install -g ganache-cli
```

Python packages
```bash
git clone git@github.com:lidofinance/depositor-bot.git
cd depositor-bot
poetry install
```

## Run script

To run (development):  

Envs:
```bash
export WEB3_INFURA_PROJECT_ID=...
export KAFKA_BROKER_ADDRESS_1=...
export KAFKA_USERNAME=...
export KAFKA_PASSWORD=...
export KAFKA_TOPIC=...
```

Run:  
```bash
# For depositor bot
brownie run depositor --network=mainnet

# For pause bot
brownie run pause --network=mainnet
```

##  Deploy

To run bot in dry mode in docker:
1. Required envs:`NETWORK` (e.g. mainnet) and `WEB3_INFURA_PROJECT_ID`.
2. Run
```bash
docker-compose up
```
*Optional*: provide `WALLET_PRIVATE_KEY` env to run with account.  
*Optional*: provide `CREATE_TRANSACTIONS` env ('true') to send tx to mempool.

## Available variables 

| Vars in env                       |   Amount   | Default - Raw | Description                                                                                                                                     |
|-----------------------------------|:----------:|:-------------:|:------------------------------------------------------------------------------------------------------------------------------------------------|
| NETWORK (required)                |     -      |    `None`     | Network (e.g. mainnet, goerli)                                                                                                                  |
| WEB3_INFURA_PROJECT_ID (required) |     -      |    `None`     | Project ID in infura                                                                                                                            |
| KAFKA_BROKER_ADDRESS_1 (required) |     -      |    `None`     | Kafka servers url and port                                                                                                                      |
| KAFKA_USERNAME (required)         |     -      |    `None`     | Kafka username value                                                                                                                                  |
| KAFKA_PASSWORD (required)         |     -      |    `None`     | Kafka password value                                                                                                                                  |
| KAFKA_TOPIC (required)            |     -      |    `None`     | Kafka topic name (for msg receiving)                                                                                                            |
| FLASHBOT_SIGNATURE (required)     |     -      |    `None`     | Private key - Used to identify account in flashbot`s rpc (should NOT be equal to WALLET private key)                                            |
| KAFKA_GROUP_PREFIX                |     -      |    `None`     | Just for staging (staging-)                                                                                                                     |
| MAX_BUFFERED_ETHERS               |  5000 ETH  | `5000 ether`  | Maximum amount of ETH in the buffer, after which the bot deposits at any gas                                                                    |
| MAX_GAS_FEE                       |  100 GWEI  |  `100 gwei`   | Bot will wait for a lower price. Treshold for gas_fee                                                                                           |
| GAS_FEE_PERCENTILE_1              |     20     |     `20`      | Percentile for first recommended fee calculation                                                                                                |
| GAS_FEE_PERCENTILE_DAYS_HISTORY_1 |     1      |      `1`      | Percentile for first recommended calculates from N days of the fee history                                                                      |
| GAS_PRIORITY_FEE_PERCENTILE       |     55     |     `55`      | Priority transaction will be N percentile from priority fees in last block (min 2 gwei - max 10 gwei)                                           |
| CONTRACT_GAS_LIMIT                | 10 * 10**6 |  `10000000`   | Default transaction gas limit                                                                                                                   |
| WALLET_PRIVATE_KEY                |     -      |    `None`     | Account private key                                                                                                                             |
| CREATE_TRANSACTIONS               |     -      |    `None`     | If `true` then tx will be send to blockchain                                                                                                    |
| MIN_PRIORITY_FEE                  |   2 GWEI   |   `2 gwei`    | Min priority fee that will be used in tx                                                                                                        |
| MAX_PRIORITY_FEE                  |  10 GWEI   |   `10 gwei`   | Max priority fee that will be used in tx (4 gwei recommended)                                                                                   |
| WEB3_RPC_ENDPOINTS                |     -      |      ``       | List of rpc endpoints that will be used to send requests separated by comma (`,`). If not provided will be used infura (WEB3_INFURA_PROJECT_ID) |
