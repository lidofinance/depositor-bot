from web3 import Web3

import variables
from blockchain.executor import Executor
from bots.pauser import PauserBot
from metrics.logging import logging


logger = logging.getLogger(__name__)


def run_pauser(w3: Web3):
    pause = PauserBot(w3)
    e = Executor(
        w3,
        pause.execute,
        1,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute pauser as daemon.'})
    e.execute_as_daemon()
