from prometheus_client import start_http_server
from flashbots import flashbot
from web3 import Web3
from web3_multi_provider import MultiProvider

import variables
from blockchain.constants import FLASHBOTS_RPC
from blockchain.contracts import contracts
from metrics.healthcheck_pulse import start_pulse_server
from metrics.logging import logging
from blockchain.requests_metric_middleware import add_requests_metric_middleware

logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': 'Start Depositor bot.'})

    logger.info({'msg': f'Start up healthcheck service on port: {variables.PULSE_SERVER_PORT}.'})
    start_pulse_server()

    logger.info({'msg': f'Start up metrics service on port: {variables.PROMETHEUS_PORT}.'})
    start_http_server(variables.PROMETHEUS_PORT)

    logger.info({'msg': 'Connect MultiHTTPProviders.', 'rpc_count': len(variables.WEB3_RPC_ENDPOINTS)})
    w3 = Web3(MultiProvider(variables.WEB3_RPC_ENDPOINTS))

    if variables.FLASHBOT_SIGNATURE is None:
        logger.info({'msg': 'No flashbots middleware.'})
    elif variables.WEB3_CHAIN_ID in FLASHBOTS_RPC:
        logger.info({'msg': 'Add flashbots middleware.'})
        flashbot(w3, w3.eth.account.from_key(variables.FLASHBOT_SIGNATURE), FLASHBOTS_RPC[variables.WEB3_CHAIN_ID])
    else:
        logger.info({'msg': 'No flashbots available for this network.'})

    logger.info({'msg': 'Add metrics to web3 requests.'})
    add_requests_metric_middleware(w3)

    logger.info({'msg': 'Load contracts.'})
    contracts.initialize(w3)

    from bots.depositor_bot import DepositorBot
    depositor_bot = DepositorBot(w3)
    depositor_bot.run_as_daemon()


if __name__ == '__main__':
    main()
