from prometheus_client import start_http_server

from scripts.pauser_utils.pause_bot import DepositPauseBot
from scripts.utils.logging import logging


logger = logging.getLogger(__name__)


def main():
    logger.info({'msg': 'Start up metrics service on port: 8080.'})
    start_http_server(8080)
    deposit_pause_bot = DepositPauseBot()
    deposit_pause_bot.run_as_daemon()
