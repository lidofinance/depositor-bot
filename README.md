# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Lido Depositor bot

## Depositor bot description
Depositor bot - Deposits buffered ether via depositBufferedEther call on "DepositSecurityModule" smart contract using special gas strategy.

The strategy is to check two things: how much buffered ether on smart contract are and gas fee.

We deposit when all the following points are correct:
- We received council signatures enough for quorum.
- Gas fee is lower or equal than 5-th percentile for past day.
- Buffered ETH is greater than or equal to the calculation according to a special formula depending on the gas fee.

## Pauser bot
If one of the councils send pause message (means something very bad going on), pauser bot try to send tx that will pause protocol.  
In addition, the council daemon tries to pause the protocol on its own.


## How to install

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
export NETWORK=...
export WEB3_RPC_ENDPOINTS=...
export FLASHBOT_SIGNATURE=...
export KAFKA_BROKER_ADDRESS_1=...
export KAFKA_USERNAME=...
export KAFKA_PASSWORD=...
export KAFKA_TOPIC=...
export RABBIT_MQ_URL=...
export RABBIT_MQ_USERNAME=...
export RABBIT_MQ_PASSWORD=...
```

Run:  
```bash
# For depositor bot
python src/depositor.py

# For pause bot
python src/pauser.py
```

## Available variables 

| Vars in env                       |   Amount   |       Default - Raw       | Description                                                                                                                                     |
|-----------------------------------|:----------:|:-------------------------:|:------------------------------------------------------------------------------------------------------------------------------------------------|
| WEB3_RPC_ENDPOINTS (required)     |     -      |            ``             | List of rpc endpoints that will be used to send requests separated by comma (`,`). If not provided will be used infura (WEB3_INFURA_PROJECT_ID) |
| NETWORK (required)                |     -      |          `None`           | Network (e.g. mainnet, goerli)                                                                                                                  |
| WALLET_PRIVATE_KEY                |     -      |          `None`           | Account private key                                                                                                                             |
| FLASHBOT_SIGNATURE (required)     |     -      |          `None`           | Private key - Used to identify account in flashbot`s rpc (should NOT be equal to WALLET private key)                                            |
| CREATE_TRANSACTIONS               |     -      |          `None`           | If `true` then tx will be send to blockchain                                                                                                    |
| MAX_BUFFERED_ETHERS               |  5000 ETH  |       `5000 ether`        | Maximum amount of ETH in the buffer, after which the bot deposits at any gas                                                                    |
| MAX_GAS_FEE                       |  100 GWEI  |        `100 gwei`         | Bot will wait for a lower price. Treshold for gas_fee                                                                                           |
| GAS_FEE_PERCENTILE_1              |     5      |            `5`            | Percentile for first recommended fee calculation                                                                                                |
| GAS_FEE_PERCENTILE_DAYS_HISTORY_1 |     1      |            `1`            | Percentile for first recommended calculates from N days of the fee history                                                                      |
| GAS_PRIORITY_FEE_PERCENTILE       |     25     |           `25`            | Priority transaction will be N percentile from priority fees in last block (min `MIN_PRIORITY_FEE` - max `MAX_PRIORITY_FEE`)                    |
| CONTRACT_GAS_LIMIT                | 15 * 10**6 |        `15000000`         | Default transaction gas limit                                                                                                                   |
| MIN_PRIORITY_FEE                  |  50 mwei   |         `50 mwei`         | Min priority fee that will be used in tx                                                                                                        |
| MAX_PRIORITY_FEE                  |  10 GWEI   |         `10 gwei`         | Max priority fee that will be used in tx (4 gwei recommended)                                                                                   |
| MAX_CYCLE_LIFETIME_IN_SECONDS     | 6 minutes  |           `300`           | Max lifetime of usual cycle. If cycle will not end in this time, bot will crush                                                                 |
| TRANSPORTS                        |     -      |         `rabbit`          | Transports used in bot. One of/or both: rabbit/kafka.                                                                                           |
| RABBIT_MQ_URL                     |            | `ws://127.0.0.1:15674/ws` | url with ws protocol supported                                                                                                                  |
| RABBIT_MQ_USERNAME                |   guest    |          `guest`          | RabbitMQ username for virtualhost                                                                                                               |
| RABBIT_MQ_PASSWORD                |   guest    |          `guest`          | RabbitMQ password for virtualhost                                                                                                               |
| KAFKA_BROKER_ADDRESS_1            |     -      |          `None`           | Kafka servers url and port                                                                                                                      |
| KAFKA_USERNAME                    |     -      |          `None`           | Kafka username value                                                                                                                            |
| KAFKA_PASSWORD                    |     -      |          `None`           | Kafka password value                                                                                                                            |
| KAFKA_TOPIC                       |     -      |          `None`           | Kafka topic name (for msg receiving)                                                                                                            |
| KAFKA_GROUP_PREFIX                |     -      |          `None`           | Just for staging (staging-)                                                                                                                     |

## Release flow

To create new release:

1. Merge all changes to the `main` branch
2. Navigate to Repo => Actions
3. Run action "Prepare release" action against `main` branch
4. When action execution is finished, navigate to Repo => Pull requests
5. Find pull request named "chore(release): X.X.X" review and merge it with "Rebase and merge" (or "Squash and merge")
6. After merge release action will be triggered automatically
7. Navigate to Repo => Actions and see last actions logs for further details 