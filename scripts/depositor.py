from brownie import web3
from prometheus_client import start_http_server
from flashbots import flashbot
from web3_multi_provider import MultiHTTPProvider

from scripts.utils import variables
from scripts.utils.constants import FLASHBOTS_RPC
from scripts.utils.healthcheck_pulse import start_pulse_server
from scripts.utils.logging import logging


logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': 'Start Depositor bot.'})

    logger.info({'msg': f'Start up healthcheck service on port: {variables.PULSE_SERVER_PORT}.'})
    start_pulse_server()

    logger.info({'msg': f'Start up metrics service on port: {variables.PROMETHEUS_PORT}.'})
    start_http_server(variables.PROMETHEUS_PORT)

    if variables.WEB3_RPC_ENDPOINTS:
        web3.disconnect()
        web3.provider = MultiHTTPProvider(variables.WEB3_RPC_ENDPOINTS)

    flashbot(web3, web3.eth.account.from_key(variables.FLASHBOT_SIGNATURE), FLASHBOTS_RPC[variables.WEB3_CHAIN_ID])

    from scripts.depositor_utils.depositor_bot import DepositorBot
    depositor_bot = DepositorBot()
    depositor_bot.run_as_daemon()
