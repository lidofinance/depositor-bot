# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Lido Depositor bot

## Depositor and Pause bot
Small bots that will 

## How to install

Only for development: [Ganache CLI](https://github.com/trufflesuite/ganache-cli) is required to run [Brownie](https://github.com/eth-brownie/brownie)

```bash 
npm install -g ganache-cli
```

Python packages
```bash
git clone git@github.com:lidofinance/depositor-bot.git
cd depositor-bot
pip install -r requirements.txt
```

## Run script

To run (development):  

Envs:
```
export WEB3_INFURA_PROJECT_ID=...
export KAFKA_BROKER_ADDRESS_1=...
export KAFKA_USERNAME=...
export KAFKA_PASSWORD=...
export KAFKA_TOPIC=...
```

Run:  
```
# For depositor bot
brownie run depositor --network=mainnet

# For pause bot
brownie run pause --network=mainnet
```

##  Deploy

To run bot in dry mode in docker:
1. Required envs:`NETWORK` (e.g. mainnet) and `WEB3_INFURA_PROJECT_ID`.
2. Run
```
docker-compose up
```
*Optional*: provide `WALLET_PRIVATE_KEY` env to run with account.  
*Optional*: provide `CREATE_TRANSACTIONS` env ('true') to send tx to mempool.

## Available variables 

| Vars in env                       |   Amount   | Default - Raw | Description                                                                                           |
|-----------------------------------|:----------:|:-------------:|:------------------------------------------------------------------------------------------------------|
| NETWORK (required)                |     -      |    `None`     | Network (e.g. mainnet, goerli)                                                                        |
| WEB3_INFURA_PROJECT_ID (required) |     -      |    `None`     | Project ID in infura                                                                                  |
| KAFKA_BROKER_ADDRESS_1 (required) |     -      |    `None`     | Kafka servers url and port                                                                            |
| KAFKA_USERNAME (required)         |     -      |    `None`     | Kafka username                                                                                        |
| KAFKA_PASSWORD (required)         |     -      |    `None`     | Kafka password                                                                                        |
| KAFKA_TOPIC (required)            |     -      |    `None`     | Kafka topic name (for msg receiving)                                                                  |
| KAFKA_GROUP_ID                    |     -      |    `None`     | By default is generated for kafka topic and client name                                               |
| MAX_GAS_FEE                       |  100 GWEI  |  `100 gwei`   | Bot will wait for a lower price. Treshold for gas_fee                                                 |
| GAS_FEE_PERCENTILE_1              |     20     |     `20`      | Percentile for first recommended fee calculation                                                      |
| GAS_FEE_PERCENTILE_DAYS_HISTORY_1 |     1      |      `1`      | Percentile for first recommended calculates from N days of the fee history                            |
| GAS_FEE_PERCENTILE_2              |     20     |     `20`      | Percentile for second recommended fee calculation                                                     |
| GAS_FEE_PERCENTILE_DAYS_HISTORY_2 |     2      |      `2`      | Percentile calculates from N days of the fee history                                                  |
| GAS_PRIORITY_FEE_PERCENTILE       |     55     |     `55`      | Priority transaction will be N percentile from priority fees in last block (min 2 gwei - max 10 gwei) |
| CONTRACT_GAS_LIMIT                | 10 * 10**6 |  `10000000`   | Default transaction gas limit                                                                         |
| WALLET_PRIVATE_KEY                |     -      |    `None`     | Account private key                                                                                   |
| CREATE_TRANSACTIONS               |     -      |    `None`     | If `true` then tx will be send to blockchain                                                          |
| MIN_PRIORITY_FEE                  |   2 GWEI   |   `2 gwei`    | If `true` then tx will be send to blockchain                                                          |
| MAX_PRIORITY_FEE                  |  10 GWEI   |   `10 gwei`   | If `true` then tx will be send to blockchain                                                          |
