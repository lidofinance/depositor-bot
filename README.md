## Depositor bot
Bot that will deposit 150 wei while gas price is low.

## How to install

[Ganache CLI](https://github.com/trufflesuite/ganache-cli) is required to run [Brownie](https://github.com/eth-brownie/brownie)

```bash 
npm install -g ganache-cli
```

Via pipenv
```bash
git clone git@github.com:lidofinance/depositor-bot.git
cd depositor-bot
pipenv install
```

## Run script

To run script type:
```
export ACCOUNT_FILENAME=path/to/account.json
brownie run depositor
```

## Defaults

| Constant                      | Amount     | Description |
| -------------                 | :--------: | :-----|
| MAX_GAS_PRICE                 | 100 GWEI   | Bot will wait for a lower price |
| CONTRACT_GAS_LIMIT            | 10 MWEI    | Default transaction gas limit |
| DEPOSIT_AMOUNT                | 150 WEI    | Each deposit equals |
| MIN_BUFFERED_ETHER            | 32 * 8 ETH | This contract should contain at least 256 ETH <br>buffered to be able to deposit |


### Lido and stETH token

Lido and stETH token address: `0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84`
