from brownie import web3
from prometheus_client import start_http_server
from web3_multi_provider import MultiProvider

from scripts.utils import variables
from scripts.utils.healthcheck_pulse import start_pulse_server
from scripts.utils.logging import logging
from scripts.utils.requests_metric_middleware import add_requests_metric_middleware

logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': 'Start Pause bot.'})

    logger.info({'msg': f'Start up healthcheck service on port: {variables.PULSE_SERVER_PORT}.'})
    start_pulse_server()

    logger.info({'msg': f'Start up metrics service on port: {variables.PROMETHEUS_PORT}.'})
    start_http_server(variables.PROMETHEUS_PORT)

    if variables.WEB3_RPC_ENDPOINTS:
        logger.info({'msg': 'Connect MultiHTTPProviders.', 'rpc_count': len(variables.WEB3_RPC_ENDPOINTS)})
        web3.disconnect()
        web3.provider = MultiProvider(variables.WEB3_RPC_ENDPOINTS)

    logger.info({'msg': 'Add metrics to web3 requests.'})
    add_requests_metric_middleware(web3)

    from scripts.pauser_utils.pause_bot import DepositPauseBot
    deposit_pause_bot = DepositPauseBot()
    deposit_pause_bot.run_as_daemon()
