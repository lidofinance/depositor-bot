# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Lido Depositor bot

## Depositor bot
Bot that will deposit ether to contract while gas price is low enough.

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
```
export WEB3_INFURA_PROJECT_ID=...
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

## Variables 

| Vars in env                       | Amount     | Default - Raw  | Description |
| -------------                     | :--------: | :---------:    | :----- |
| NETWORK (required)                | -          | `None`         | Network (e.g. mainnet, goerli) |
| WEB3_INFURA_PROJECT_ID (required) | -          | `None`         | Project ID in infura |
| KAFKA_BROKER_ADDRESS_1 (required) | -         | `None`         | Kafka servers url and port |
| KAFKA_USERNAME (required)    | -          | `None`         | Kafka username |
| KAFKA_PASSWORD (required)    | -          | `None`         | Kafka password |
| KAFKA_TOPIC (required)            | -          | `None`         | Kafka topic name (for msg receiving) |
| MAX_GAS_FEE                       | 100 GWEI   | `100 gwei`     | Bot will wait for a lower price |
| GAS_FEE_PERCENTILE                | 30         | `30`           | Deposit when gas fee is lower that 30 percentile |
| GAS_FEE_PERCENTILE_DAYS_HISTORY   | 2          | `2`            | Percentile calculates from N days of fee history |
| GAS_PRIORITY_FEE_PERCENTILE       | 55         | `55`           | Priority transaction will be N percentile from priority fees in last block |
| CONTRACT_GAS_LIMIT                | 10 MWEI    | `10 mwei`      | Default transaction gas limit |
| MIN_BUFFERED_ETHER                | 1024 ETH   | `1025 ether`   | Minimum ETH in buffer to deposit |
| WALLET_PRIVATE_KEY               | -          | `None`         | Account private key |
| CREATE_TRANSACTIONS               | false          | `false`         | If `true` then tx should be created in blockchain |


## Contract details

| Constants                     | Amount     | Description |
| -------------                 | :--------: | :----- |
| MIN_BUFFERED_ETHER            | 256 ETH    | This contract should contain at least 256 ETH buffered to be able to deposit |
| LIDO_CONTRACT_ADDRESS         | 0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84 | Lido contract address |
