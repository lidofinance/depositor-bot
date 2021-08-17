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


| Constants                     | Amount     | Description |
| -------------                 | :--------: | :----- |
| MIN_BUFFERED_ETHER            | 256 ETH    | This contract should contain at least 256 ETH buffered to be able to deposit |
| LIDO_CONTRACT_ADDRESS         | 0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84 | Lido contract address |

  
## Production only
| Variable | Description |
| :---: | :---:|
| ACCOUNT_FILENAME | Path to account file, e.g. `/home/account.json` |
| ACCOUNT_PASSWORD | Password if private key is encrypted |