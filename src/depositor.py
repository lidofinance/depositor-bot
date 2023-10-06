# from flashbots import flashbot
from prometheus_client import start_http_server
from web3 import Web3
from web3_multi_provider import FallbackProvider

import variables
from blockchain.executor import Executor
from blockchain.web3_extentions.bundle import activate_relay
from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.requests_metric_middleware import add_requests_metric_middleware
from blockchain.web3_extentions.transaction import TransactionUtils
from bots.depositor import DepositorBot
from metrics.healthcheck_pulse import start_pulse_server
from metrics.logging import logging
from metrics.metrics import BUILD_INFO

logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': f'Start up healthcheck service on port: {variables.PULSE_SERVER_PORT}.'})
    start_pulse_server()

    logger.info({'msg': f'Start up metrics service on port: {variables.PROMETHEUS_PORT}.'})
    start_http_server(variables.PROMETHEUS_PORT)

    # Send vars to metrics
    BUILD_INFO.labels(
        'Depositor bot',
        variables.MAX_GAS_FEE,
        variables.MAX_BUFFERED_ETHERS,
        variables.CONTRACT_GAS_LIMIT,
        variables.GAS_FEE_PERCENTILE_1,
        variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1,
        variables.GAS_PRIORITY_FEE_PERCENTILE,
        variables.MIN_PRIORITY_FEE,
        variables.MAX_PRIORITY_FEE,
        variables.ACCOUNT.address if variables.ACCOUNT else '0x0',
        variables.CREATE_TRANSACTIONS,
        variables.DEPOSIT_MODULES_WHITELIST,
    )

    logger.info({'msg': 'Connect MultiHTTPProviders.', 'rpc_count': len(variables.WEB3_RPC_ENDPOINTS)})
    w3 = Web3(FallbackProvider(variables.WEB3_RPC_ENDPOINTS))

    logger.info({'msg': 'Initialize Lido contracts.'})
    w3.attach_modules({
        'lido': LidoContracts,
        'transaction': TransactionUtils,
    })

    if variables.FLASHBOT_SIGNATURE and variables.FLASHBOTS_RPC:
        logger.info({'msg': 'Add private relays.'})
        activate_relay(w3, variables.FLASHBOT_SIGNATURE, [variables.FLASHBOTS_RPC])
    else:
        logger.info({'msg': 'No flashbots available for this network.'})

    logger.info({'msg': 'Add metrics to web3 requests.'})
    add_requests_metric_middleware(w3)

    logger.info({'msg': 'Initialize Depositor bot.'})
    depositor_bot = DepositorBot(w3)

    e = Executor(
        w3,
        depositor_bot.execute,
        5,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute depositor as daemon.'})
    e.execute_as_daemon()


if __name__ == '__main__':
    main()
