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

To run script:
```
export WEB3_INFURA_PROJECT_ID=b11919ed73094499a35d1b3fa338322a
brownie run depositor --network=mainnet-fork
```

To run in  production
```
docker build -t depositor-bot .
docker run depositor-bot
```

## Variables 

| Vars in env                   | Amount     | Default - Raw            | Description |
| -------------                 | :--------: | :---------:    | :----- |
| MAX_GAS_PRICE                 | 100 GWEI   | `100000000000` | Bot will wait for a lower price |
| CONTRACT_GAS_LIMIT            | 10 MWEI    | `10000000`     | Default transaction gas limit |
| DEPOSIT_AMOUNT                | 150        | `150`          | Look into contract to get more info |
| ACCOUNT_PATH_TO_FILE          | -          | `None`         | If no path was provided - will take first account that available |
| ACCOUNT_PASSWORD              | -          | `None`         | Password if private key is encrypted in file |
| WEB3_INFURA_PROJECT_ID        | -          | `None`         | Project ID in infura |


## Contract details

| Constants                     | Amount     | Description |
| -------------                 | :--------: | :----- |
| MIN_BUFFERED_ETHER            | 256 ETH    | This contract should contain at least 256 ETH buffered to be able to deposit |
| LIDO_CONTRACT_ADDRESS         | 0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84 | Lido contract address |
