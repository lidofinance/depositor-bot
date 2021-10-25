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
brownie run depositor --network=mainnet
```

##  Deploy

To run bot in dry mode in docker:
1. Required envs:`NETWORK` (e.g. mainnet) and `WEB3_INFURA_PROJECT_ID`.
2. Run
```
docker-compose up
```
*Optional*: provide `ACCOUNT_PRIVATE_KEY` env to run bot in production mode.

## Variables 

| Vars in env                       | Amount     | Default - Raw  | Description |
| -------------                     | :--------: | :---------:    | :----- |
| NETWORK (required)                | -          | `None`         | Network (e.g. mainnet) |
| WEB3_INFURA_PROJECT_ID (required) | -          | `None`         | Project ID in infura |
| KAFKA_BOOTSTRAP_SERVERS (required) | -         | `None`         | Kafka servers url and port |
| KAFKA_SASL_USERNAME (required)    | -          | `None`         | Kafka username |
| KAFKA_SASL_PASSWORD (required)    | -          | `None`         | Kafka password |
| MAX_GAS_FEE                       | 100 GWEI   | `100 gwei`     | Bot will wait for a lower price |
| MAX_KEYS_TO_DEPOSIT               | 155        | `155`          | Max keys to deposit at once |
| CONTRACT_GAS_LIMIT                | 10 MWEI    | `10 mwei`      | Default transaction gas limit |
| ACCOUNT_PRIVATE_KEY               | -          | `None`         | Account private key |
| ACCOUNT_FILENAME                  | -          | `None`         | File with account key (manual password entering required) |


## Contract details

| Constants                     | Amount     | Description |
| -------------                 | :--------: | :----- |
| MIN_BUFFERED_ETHER            | 256 ETH    | This contract should contain at least 256 ETH buffered to be able to deposit |
| LIDO_CONTRACT_ADDRESS         | 0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84 | Lido contract address |
