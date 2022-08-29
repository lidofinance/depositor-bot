from prometheus_client import start_http_server
from web3 import Web3
from web3_multi_provider import MultiProvider

import variables
from metrics.healthcheck_pulse import start_pulse_server
from metrics.logging import logging
from blockchain.requests_metric_middleware import add_requests_metric_middleware
from src.blockchain.contracts import contracts

logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': 'Start Pause bot.'})

    logger.info({'msg': f'Start up healthcheck service on port: {variables.PULSE_SERVER_PORT}.'})
    start_pulse_server()

    logger.info({'msg': f'Start up metrics service on port: {variables.PROMETHEUS_PORT}.'})
    start_http_server(variables.PROMETHEUS_PORT)

    logger.info({'msg': 'Connect MultiHTTPProviders.', 'rpc_count': len(variables.WEB3_RPC_ENDPOINTS)})
    w3 = Web3(MultiProvider(variables.WEB3_RPC_ENDPOINTS))

    logger.info({'msg': 'Add metrics to web3 requests.'})
    add_requests_metric_middleware(w3)

    logger.info({'msg': 'Load contracts.'})
    contracts.initialize(w3)

    from bots.pause_bot import DepositPauseBot
    deposit_pause_bot = DepositPauseBot(w3)
    deposit_pause_bot.run_as_daemon()
