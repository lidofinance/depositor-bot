# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Lido For Polygon Depositor bot

## Delegator and Reward Distributor bot
Small bots that will 

## How to install

Only for development: [Ganache CLI](https://github.com/trufflesuite/ganache-cli) is required to run [Brownie](https://github.com/eth-brownie/brownie)

```bash 
npm install -g ganache-cli
```

Python packages
```bash
git clone git@github.com:Shard-Labs/depositor-bot.git
cd depositor-bot
pip install -r requirements.txt
```

## Run script

To run (development):  

Run:  
```
# For depositor bot
brownie run depositor --network=mainnet
```

##  Deploy

To run bot in dry mode in docker:
1. Required envs:`NETWORK` (e.g. mainnet) and `WEB3_INFURA_PROJECT_ID`.
2. Run
```
docker-compose up
```
- *Optional*: provide `WALLET_PRIVATE_KEY` env to run with account.  
- *Optional*: provide `CREATE_TRANSACTIONS` env ('true') to send tx to mempool.
- *Optional*: cycle `CYCLE` env time interval to delegate and distribute rewards.

## Available variables 

| Vars in env                       |   Amount   | Default - Raw | Description                                                                                           |
|-----------------------------------|:----------:|:-------------:|:------------------------------------------------------------------------------------------------------|
| NETWORK (required)                |     -      |    `None`     | Network (e.g. mainnet, goerli)                                                                        |
| WEB3_INFURA_PROJECT_ID (required) |     -      |    `None`     | Project ID in infura                                                                                  |
| MAX_BUFFERED_MATICS               |1000000 ETH |`1000000 ether`| Maximum amount of MATIC in the buffer, after which the bot deposits at any gas                        |
| MAX_GAS_FEE                       |  100 GWEI  |  `100 gwei`   | Bot will wait for a lower price. Treshold for gas_fee                                                 |
| GAS_FEE_PERCENTILE_1              |     20     |     `20`      | Percentile for first recommended fee calculation                                                      |
| GAS_FEE_PERCENTILE_DAYS_HISTORY_1 |     1      |      `1`      | Percentile for first recommended calculates from N days of the fee history                            |
| GAS_FEE_PERCENTILE_2              |     20     |     `20`      | Percentile for second recommended fee calculation                                                     |
| GAS_FEE_PERCENTILE_DAYS_HISTORY_2 |     2      |      `2`      | Percentile calculates from N days of the fee history                                                  |
| GAS_PRIORITY_FEE_PERCENTILE       |     55     |     `55`      | Priority transaction will be N percentile from priority fees in last block (min 2 gwei - max 10 gwei) |
| CONTRACT_GAS_LIMIT                | 10 * 10**6 |  `10000000`   | Default transaction gas limit                                                                         |
| WALLET_PRIVATE_KEY                |     -      |    `None`     | Account private key                                                                                   |
| CREATE_TRANSACTIONS               |     -      |    `None`     | If `true` then tx will be send to blockchain                                                          |
| MIN_PRIORITY_FEE                  |   2 GWEI   |   `2 gwei`    | Min priority fee that will be used in tx                                                              |
| MAX_PRIORITY_FEE                  |  10 GWEI   |   `10 gwei`   | Max priority fee that will be used in tx (4 gwei recommended)                                         |
| CYCLE                             |   86400    |    `86400`    | The time interval between each delegation and reward distribution                                     |
| RETRY_GAS_FEE                     |  60 sec    |     `60`      | The time interval to wait before retrying to submit a transaction if the gas Fee is too high          |
| RETRY_GAS_FEE_TIMES               |    60      |     `60`      | The number of times to retry before sleep for a Cycle (RETRY_GAS_FEE * RETRY_GAS_FEE_TIMES)           |
