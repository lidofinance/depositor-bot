# <img src="https://docs.lido.fi/img/logo.svg" alt="Lido" width="46"/> Lido Depositor bot

## Description

Depositor and pauser bots are parts
of [Deposit Security Module](https://github.com/lidofinance/lido-improvement-proposals/blob/develop/LIPS/lip-5.md#mitigations-for-deposit-front-running-vulnerability).

**The Depositor Bot** obtains signed deposit messages from Council Daemons.
Once a sufficient number of messages is collected to constitute a quorum, the bot proceeds to initiate a deposit into the designated staking
module.
This deposit is executed using the depositBufferedEther function within the "DepositSecurityModule" smart contract.

Direct deposit is a mechanism that allows depositors to use side vault facilities for deposits. This process transfers ETH from the vault
and facilitates the deposit to specified in side vault staking module, preventing funds from being stuck in the withdrawal queue.

**The Pauser Bot** obtains pause message from Council Daemon and enacts pause deposits on protocol. Pause can occurs when Lido detects
stealing.

**The Unvetting Bot** obtains unvet message from Council Daemon and enacts unvet on the specified node operator.
Unvetting is the proces of decreasing approved depositable signing keys.

## Table of Contents

- [Running Daemon](#running-daemon)
- [Variables](#variables)
    - [Required variables](#required-variables)
    - [Additional variables](#additional-variables)
- [Metrics and logs](#metrics-and-logs)
- [Development](#development)
    - [Install](#install)
    - [Tests](#tests)
    - [Release flow](#release-flow)
- [Annotations to code](#annotations-to-code)

## Running Daemon

1. Create `.env` file
2. Setup variables
    - Set WEB3_RPC_ENDPOINTS
    - Set WALLET_PRIVATE_KEY
    - Set CREATE_TRANSACTIONS to true
    - Set MESSAGE_TRANSPORTS to rabbit
    - Set RABBIT_MQ_URL, RABBIT_MQ_USERNAME and RABBIT_MQ_PASSWORD
3. ```docker-compose up```
4. Send metrics and logs to grafana
5. Setup alerts

## Variables

### Required variables

| Variable                  | Default                                    | Description                                                                                                              |
|---------------------------|--------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| WEB3_RPC_ENDPOINTS        | -                                          | List of rpc endpoints that will be used to send requests comma separated (`,`)                                           |
| WALLET_PRIVATE_KEY        | -                                          | Account private key                                                                                                      |
| CREATE_TRANSACTIONS       | false                                      | If true then tx will be send to blockchain                                                                               |
| LIDO_LOCATOR              | 0xC1d0b3DE6792Bf6b4b37EccdcC24e45978Cfd2Eb | Lido Locator address. Mainnet by default. Other networks could be found [here](https://docs.lido.fi/deployed-contracts/) |
| DEPOSIT_CONTRACT          | 0x00000000219ab540356cBB839Cbe05303d7705Fa | Ethereum deposit contract address                                                                                        |
| DEPOSIT_MODULES_WHITELIST | 1                                          | List of staking module's ids in which the depositor bot will make deposits                                               |
| ---                       | ---	                                       | ---                                                                                                                      |
| MESSAGE_TRANSPORTS        | -                                          | Transports used in bot. One of/or both: rabbit/onchain_transport                                                         |
| RABBIT_MQ_URL             | -                                          | RabbitMQ url                                                                                                             |
| RABBIT_MQ_USERNAME        | -                                          | RabbitMQ username for virtualhost                                                                                        |
| RABBIT_MQ_PASSWORD        | -                                          | RabbitMQ password for virtualhost                                                                                        |

### Additional variables

| Variable                          | Default       | Description                                                                                                              |
|-----------------------------------|---------------|--------------------------------------------------------------------------------------------------------------------------|
| MIN_PRIORITY_FEE                  | 50 mwei       | Min priority fee that will be used in tx                                                                                 |
| MAX_PRIORITY_FEE                  | 10 gwei       | Max priority fee that will be used in tx                                                                                 |
| MAX_GAS_FEE                       | 100 gwei      | Bot will wait for a lower price. Treshold for gas_fee                                                                    |
| CONTRACT_GAS_LIMIT                | 15000000      | Default transaction gas limit                                                                                            |
| RELAY_RPC                         | -             | RPC URI                                                                                                                  |
| AUCTION_BUNDLER_PRIVATE_KEY       | -             | Private key - Used to identify account for relays (should NOT be equal to WALLET private key)                            |
| GAS_FEE_PERCENTILE_1              | 20            | Percentile for first recommended fee calculation                                                                         |
| GAS_FEE_PERCENTILE_DAYS_HISTORY_1 | 1             | Percentile for first recommended calculates from N days of the fee history                                               |
| GAS_PRIORITY_FEE_PERCENTILE       | 25            | Priority transaction will be N percentile from priority fees in last block (min MIN_PRIORITY_FEE - max MAX_PRIORITY_FEE) |
| MAX_BUFFERED_ETHERS               | 5000 ether    | Maximum amount of ETH in the buffer, after which the bot deposits at any gas                                             |
| PROMETHEUS_PORT                   | 9000          | Port with metrics server                                                                                                 |
| PROMETHEUS_PREFIX                 | depositor_bot | Prefix for the metrics                                                                                                   |
| HEALTHCHECK_SERVER_PORT           | 9010          | Port with bot`s status server                                                                                            |
| MAX_CYCLE_LIFETIME_IN_SECONDS     | 1200          | Max lifetime of usual cycle. If cycle will not end in this time, bot will crush                                          |
| MELLOW_CONTRACT_ADDRESS           | None          | If variable is set then deposit can go to predifined module                                                              |
| VAULT_DIRECT_DEPOSIT_THRESHOLD    | 1 ether       | If mellow vault has VAULT_DIRECT_DEPOSIT_THRESHOLD ethers then direct deposit will be sent                               |
| ONCHAIN_TRANSPORT_RPC_ENDPOINTS   | -             | RPC endpoint for the databus RPC, Gnosis at the moment                                                                   |

## Metrics and logs

Metrics list could be found in [source code](src/metrics/metrics.py).
Prometheus server hosted on `http://localhost:${{PROMETHEUS_PORT}}/`.

## Development

### Install

```bash
git clone git@github.com:lidofinance/depositor-bot.git
cd depositor-bot
poetry install
```

To run bot

```bash
poetry run python main depositor

poetry run python main pauser

poetry run python main unvetter
```

### Tests

#### Run unit tests

```bash
poetry run pytest tests -m unit
```

#### Run integration tests.

TESTNET_WEB3_RPC_ENDPOINTS - set this variable for the Ethereum EL testnet RPC

Install Anvil

```bash
poetry run pytest tests -m integration
```

In case of "command not found: anvil" error, provide `ANVIL_PATH` variable

```bash
export ANVIL_PATH='pathto/anvil'
```

### Release flow

To create a new release:

1. Merge all changes to the `main` branch.
2. After the merge, the `Prepare release draft` action will run automatically. When the action is complete, a release draft is created.
3. When you need to release, go to Repo → Releases.
4. Publish the desired release draft manually by clicking the edit button - this release is now the `Latest Published`.
5. After publication, the action to create a release bump will be triggered automatically.
