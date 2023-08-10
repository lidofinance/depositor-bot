from prometheus_client import start_http_server
from web3 import Web3
from web3_multi_provider import FallbackProvider

import variables
from blockchain.executer import Executor
from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.transaction import TransactionUtils
from bots.pause import PauserBot
from metrics.healthcheck_pulse import start_pulse_server
from metrics.logging import logging
from blockchain.web3_extentions.requests_metric_middleware import add_requests_metric_middleware
from metrics.metrics import BUILD_INFO

logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': f'Start up healthcheck service on port: {variables.PULSE_SERVER_PORT}.'})
    start_pulse_server()

    logger.info({'msg': f'Start up metrics service on port: {variables.PROMETHEUS_PORT}.'})
    start_http_server(variables.PROMETHEUS_PORT)

    BUILD_INFO.labels(
        'Pause bot',
        variables.NETWORK,
        variables.MAX_GAS_FEE,
        variables.MAX_BUFFERED_ETHERS,
        variables.CONTRACT_GAS_LIMIT,
        None,
        None,
        None,
        None,
        None,
        variables.KAFKA_TOPIC,
        variables.ACCOUNT.address if variables.ACCOUNT else '0x0',
        variables.CREATE_TRANSACTIONS,
    )

    logger.info({'msg': 'Connect MultiHTTPProviders.', 'rpc_count': len(variables.WEB3_RPC_ENDPOINTS)})
    w3 = Web3(FallbackProvider(variables.WEB3_RPC_ENDPOINTS))

    logger.info({'msg': 'Add metrics to web3 requests.'})
    add_requests_metric_middleware(w3)

    logger.info({'msg': 'Load contracts.'})
    w3.attach_modules({
        'lido': LidoContracts,
        'transaction': TransactionUtils,
    })

    logger.info({'msg': 'Add metrics to web3 requests.'})
    add_requests_metric_middleware(w3)

    pause = PauserBot(w3)
    e = Executor(
        w3,
        pause.execute,
        1,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Rum executor.'})
    e.execute_as_daemon()


if __name__ == '__main__':
    main()
