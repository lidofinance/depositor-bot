from brownie import web3
from prometheus_client import start_http_server
from web3_multi_provider import MultiHTTPProvider

from scripts.pauser_utils.pause_bot import DepositPauseBot
from scripts.utils import variables
from scripts.utils.healthcheck_pulse import start_pulse_server
from scripts.utils.logging import logging


logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': 'Start up healthcheck service on port: 9010.'})
    start_pulse_server()

    logger.info({'msg': 'Start up metrics service on port: 9000.'})
    start_http_server(9000)

    if variables.WEB3_RPC_ENDPOINTS:
        web3.disconnect()
        web3.provider = MultiHTTPProvider(variables.WEB3_RPC_ENDPOINTS)

    deposit_pause_bot = DepositPauseBot()
    deposit_pause_bot.run_as_daemon()
