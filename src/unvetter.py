import time

import variables
from blockchain.executor import Executor
from blockchain.typings import Web3
from bots.unvetter import UnvetterBot
from metrics.healthcheck_pulse import pulse
from metrics.logging import logging


logger = logging.getLogger(__name__)


def run_unvetter(w3: Web3):
    unvetter = UnvetterBot(w3)
    e = Executor(
        w3,
        unvetter.execute,
        1,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute unvetter as daemon.'})
    e.execute_as_daemon()
