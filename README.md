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
git clone git@github.com:lidofinance/depositor_utils-bot.git
cd depositor_utils-bot
pip install -r requirements.txt
```

## Run script

To run (development): 
```
export WEB3_INFURA_PROJECT_ID=b11919ed73094499a35d1b3fa338322a
brownie run depositor --network=mainnet-fork
```

To run (production):
1. Change `WEB3_INFURA_PROJECT_ID` and `ACCOUNT_PRIVATE_KEY` envs in Dockerfile
2. Run
```
docker build -t depositor-bot .
docker run depositor-bot
```

## Variables 

| Vars in env                   | Amount     | Default - Raw  | Description |
| -------------                 | :--------: | :---------:    | :----- |
| MAX_GAS_FEE                   | 100 GWEI   | `100 gwei`     | Bot will wait for a lower price |
| CONTRACT_GAS_LIMIT            | 10 MWEI    | `10 mwei`      | Default transaction gas limit |
| DEPOSIT_AMOUNT                | 155        | `155`          | Look into contract to get more info |
| ACCOUNT_PRIVATE_KEY           | -          | `None`         | Account private key |
| ACCOUNT_FILENAME              | -          | `None`         | File with account key (manual password entering required) |
| WEB3_INFURA_PROJECT_ID        | -          | `None`         | Project ID in infura |
| GAS_PREDICTION_PERCENTILE     | 20         | `20`           | Recommended price calculates from the percentile in the week gas fee history |


## Contract details

| Constants                     | Amount     | Description |
| -------------                 | :--------: | :----- |
| MIN_BUFFERED_ETHER            | 256 ETH    | This contract should contain at least 256 ETH buffered to be able to deposit |
| LIDO_CONTRACT_ADDRESS         | 0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84 | Lido contract address |
