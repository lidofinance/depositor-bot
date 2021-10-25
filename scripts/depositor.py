from brownie.network import web3
from prometheus_client import start_http_server

from scripts.depositor_utils.depositor_bot import DepositorBot
from scripts.depositor_utils.logger import logger


def main():
    logger.info({"msg": 'Start up metrics service on port: 8080.'})
    start_http_server(8080)
    depositor_bot = DepositorBot(web3)
    depositor_bot.run_as_daemon()
