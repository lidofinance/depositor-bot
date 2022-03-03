from prometheus_client import start_http_server

from scripts.depositor_utils.depositor_bot import DepositorBot
from scripts.utils.logging import logging


logger = logging.getLogger(__name__)

def main():
    logger.info({'msg': 'Start up metrics service on port: 8080.'})
    start_http_server(8080)

    delegator_bot = DepositorBot()
    delegator_bot.run_as_daemon()