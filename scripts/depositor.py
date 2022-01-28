from brownie import web3
from prometheus_client import start_http_server
from flashbots import flashbot

from scripts.depositor_utils.depositor_bot import DepositorBot
from scripts.utils import variables
from scripts.utils.constants import FLASHBOTS_RPC
from scripts.utils.logging import logging


logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': 'Start up metrics service on port: 8080.'})
    start_http_server(8080)
    flashbot(web3, web3.eth.account.from_key(variables.FLASHBOT_SIGNATURE), FLASHBOTS_RPC[variables.WEB3_CHAIN_ID])
    depositor_bot = DepositorBot()
    depositor_bot.run_as_daemon()
